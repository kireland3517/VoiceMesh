"""Voice API routes - handles SignalWire webhooks and voice session management."""

import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import structlog

from src.api.database import get_db
from src.api.models import Customer, Call
from src.api.config import settings
from src.platform.voice_pipeline import VoiceMeshPipeline
from src.platform.daily_integration import DailyRoomManager

logger = structlog.get_logger()
router = APIRouter(prefix="/voice", tags=["voice"])

# Daily.co room manager
daily_manager = DailyRoomManager(api_key=settings.DAILY_API_KEY)


class PromptTestRequest(BaseModel):
    """Test a prompt configuration."""
    customer_id: str
    prompt: str
    test_input: str


class PromptTestResponse(BaseModel):
    """Response from prompt test."""
    output: str
    tokens_used: int
    response_time_ms: float


class UseCasePrompt(BaseModel):
    """Pre-built use case prompt."""
    name: str
    description: str
    system_prompt: str


# Pre-built use case prompts
USE_CASE_PROMPTS = [
    UseCasePrompt(
        name="Customer Service Agent",
        description="Handle customer inquiries, check order status, process returns",
        system_prompt="""You are a friendly customer service agent for Acme Corporation.

Your primary responsibilities:
1. Greet the customer warmly
2. Listen to their inquiry or concern
3. Provide helpful information or solutions
4. Escalate to a human agent when necessary

Key information to gather:
- Get customer name and phone number
- Understand the specific issue or question
- Determine urgency level

Always maintain a professional, empathetic tone and focus on resolving the customer's needs efficiently."""
    ),
    UseCasePrompt(
        name="Sales Assistant",
        description="Qualify leads, schedule demos, answer product questions",
        system_prompt="""You are an enthusiastic sales assistant for TechCorp's software solutions.

Your goals:
1. Understand the prospect's business needs
2. Qualify their budget and timeline
3. Highlight relevant product benefits
4. Schedule a demo or meeting with sales team

Key qualification questions:
- What industry are they in?
- What's their current solution/pain point?
- What's their budget range?
- What's their timeline for implementation?

Be consultative, not pushy. Focus on understanding their needs before presenting solutions."""
    ),
    UseCasePrompt(
        name="Appointment Scheduler",
        description="Schedule appointments, handle cancellations, send confirmations",
        system_prompt="""You are a professional appointment scheduler for MedCenter clinic.

Your responsibilities:
1. Check appointment availability
2. Schedule new appointments
3. Handle cancellations and rescheduling
4. Collect necessary patient information

Information to gather:
- Patient name and contact information
- Preferred appointment date/time
- Type of appointment needed
- Insurance information (if new patient)

Always confirm all details before finalizing appointments and provide clear next steps."""
    )
]


@router.post("/prompt/test")
async def test_prompt(
    request: PromptTestRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Test a custom prompt configuration.
    
    Example request:
    ```json
    {
        "customer_id": "cust_abc123",
        "prompt": "You are a helpful assistant...",
        "test_input": "Hello, can you help me?"
    }
    ```
    """
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.id == request.customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # TODO: Implement actual prompt testing with Claude API
    # This would send the prompt + input to Claude and return the response
    
    return PromptTestResponse(
        output="This is a test response. Prompt testing not yet implemented.",
        tokens_used=45,
        response_time_ms=234.5
    )


@router.get("/prompts/use-cases")
async def get_use_case_prompts():
    """Get pre-built use case prompts for common scenarios."""
    return {
        "use_cases": USE_CASE_PROMPTS,
        "total": len(USE_CASE_PROMPTS)
    }


@router.post("/incoming-call")
async def handle_incoming_call(
    customer_id: str = Query(..., description="Customer ID from query params"),
):
    """
    Handle incoming call from SignalWire.
    
    This is the primary webhook URL for SignalWire:
    https://voicemesh.fly.dev/voice/incoming-call?customer_id=YOUR_CUSTOMER_ID
    
    Args:
        customer_id: Query parameter to identify which customer owns this number
        
    Returns:
        SWML script that tells SignalWire to call the session creation endpoint
    """
    logger.info("swml_primary_script_requested", customer_id=customer_id)
    
    # Return SWML script that makes a request to our session creation endpoint
    swml_script = {
        "version": "1.0.0",
        "sections": {
            "main": [
                {
                    "request": {
                        "url": f"https://voicemesh.fly.dev/voice/create-session?customer_id={customer_id}&call_id=%{{call.call_id}}&from=%{{call.from}}&to=%{{call.to}}",
                        "method": "POST"
                    }
                }
            ]
        }
    }
    
    return JSONResponse(content=swml_script)


@router.post("/create-session")
async def create_voice_session(
    customer_id: str = Query(..., description="Customer ID"),
    call_id: str = Query(..., description="Call ID from SignalWire"),
    from_number: str = Query("", alias="from", description="Caller's phone number"),
    to_number: str = Query("", alias="to", description="Dialed phone number"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a voice session and start the AI pipeline.
    
    This endpoint is called by SignalWire after the primary webhook.
    
    Args:
        customer_id: Customer ID from query params
        call_id: Unique call identifier from SignalWire
        from_number: Caller's phone number
        to_number: Dialed phone number
        
    Returns:
        SWML script with SIP URI for the voice session
    """
    logger.info(
        "creating_voice_session",
        customer_id=customer_id,
        call_id=call_id,
        from_number=from_number,
        to_number=to_number
    )

    try:
        # Pre-load customer with all functions to avoid database calls in pipeline
        customer_result = await db.execute(
            select(Customer)
            .options(selectinload(Customer.functions))
            .where(Customer.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        
        if not customer:
            logger.error("customer_not_found", customer_id=customer_id)
            return JSONResponse(
                content={"error": "Customer not found"}, 
                status_code=404
            )

        # Create call record
        call = Call(
            id=str(uuid.uuid4()),
            customer_id=customer_id,
            call_sid=call_id,
            from_number=from_number,
            to_number=to_number,
            status="initiated",
        )
        
        db.add(call)
        await db.commit()
        await db.refresh(call)
        
        logger.info("call_record_created", call_id=call.id, customer_id=customer_id)

        # Create Daily.co room for the call
        room_data = await daily_manager.create_room(
            call_id=call.id,
            enable_recording=False
        )

        room_url = room_data["url"]
        sip_uri = room_data["sip_uri"]
        room_token = room_data["token"]

        logger.info(
            "daily_room_created_for_call",
            call_id=call.id,
            room_url=room_url,
            sip_uri=sip_uri
        )

        # Start voice pipeline in background
        background_tasks.add_task(
            start_voice_pipeline_background,
            customer_id=customer.id,
            call_id=call.id,
            room_url=room_url,
            room_token=room_token,
            customer=customer  # Pass pre-loaded customer object
        )

        # Return SWML script with SIP dial command
        swml_response = {
            "version": "1.0.0",
            "sections": {
                "main": [
                    {
                        "dial": {
                            "sip": sip_uri
                        }
                    }
                ]
            }
        }

        logger.info(
            "swml_response_sent",
            call_id=call.id,
            sip_uri=sip_uri
        )

        return JSONResponse(content=swml_response)

    except Exception as e:
        logger.error(
            "session_creation_failed",
            customer_id=customer_id,
            call_id=call_id,
            error=str(e)
        )
        return JSONResponse(
            content={"error": "Failed to create voice session"}, 
            status_code=500
        )


async def start_voice_pipeline_background(
    customer_id: str,
    call_id: str,
    room_url: str,
    room_token: str,
    customer: Customer  # Pre-loaded customer object with functions
):
    """
    Start the voice pipeline in the background.
    
    Args:
        customer_id: ID of the customer making the call
        call_id: ID of the call record
        room_url: Daily.co room URL
        room_token: Daily.co room access token
        customer: Pre-loaded Customer object with functions
    """
    try:
        logger.info(
            "starting_voice_pipeline",
            call_id=call_id,
            customer_id=customer.id
        )

        logger.info(
            "setting_up_voice_pipeline",
            customer_id=customer.id,
            room_url=room_url
        )

        # Get voice config from customer or use defaults (use getattr for backward compatibility)
        voice_config = getattr(customer, 'voice_config', None) or {}

        # Create and configure pipeline with customer settings
        pipeline = VoiceMeshPipeline(
            customer=customer,  # Pre-loaded customer with functions
            deepgram_config={
                "model": "nova-2",
                "language": customer.default_language or "en",
                "smart_format": True,
                "punctuate": True
            },
            cartesia_config={
                "voice_id": customer.default_voice or "a0e99841-438c-4a64-b679-ae501e7d6091",
                "model_id": "sonic-english",
                "speed": voice_config.get("speech_speed", None),
                "emotion": voice_config.get("emotion", None)
            }
        )

        # Setup pipeline with the room token
        await pipeline.setup_pipeline(
            room_url=room_url,
            token=room_token,
            bot_name="VoiceMesh Assistant"
        )

        logger.info(
            "voice_pipeline_setup_complete",
            call_id=call_id,
            customer_id=customer.id
        )

        # Start the pipeline (this will run until the call ends)
        await pipeline.start()

        logger.info(
            "voice_pipeline_completed",
            call_id=call_id,
            customer_id=customer.id
        )

    except Exception as e:
        logger.error(
            "voice_pipeline_failed",
            call_id=call_id,
            error=str(e)
        )
        
        # Clean up - delete the Daily.co room if pipeline failed
        try:
            room_name = f"voicemesh-{call_id}"
            await daily_manager.delete_room(room_name)
            logger.info("daily_room_deleted", room_name=room_name)
        except Exception as cleanup_error:
            logger.error("room_cleanup_failed", error=str(cleanup_error))


@router.get("/health")
async def health_check():
    """Health check endpoint for voice services."""
    return {
        "status": "healthy",
        "service": "voice",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/stats")
async def get_voice_stats(db: AsyncSession = Depends(get_db)):
    """Get voice service statistics."""
    
    # Count total calls
    total_calls_result = await db.execute(
        select(func.count(Call.id))
    )
    total_calls = total_calls_result.scalar()

    # Count calls by status
    active_calls_result = await db.execute(
        select(func.count(Call.id)).where(Call.status == "active")
    )
    active_calls = active_calls_result.scalar()

    completed_calls_result = await db.execute(
        select(func.count(Call.id)).where(Call.status == "completed")
    )
    completed_calls = completed_calls_result.scalar()

    failed_calls_result = await db.execute(
        select(func.count(Call.id)).where(Call.status == "failed")
    )
    failed_calls = failed_calls_result.scalar()

    return {
        "total_calls": total_calls,
        "active_calls": active_calls,
        "completed_calls": completed_calls,
        "failed_calls": failed_calls,
        "service": "voice_api"
    }