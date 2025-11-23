"""Voice AI testing and call management endpoints."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.api.database import get_db
from src.api.models import Customer, Call
from anthropic import Anthropic
from src.api.config import settings
from src.platform.daily_integration import DailyRoomManager
from src.platform.voice_pipeline import VoiceMeshPipeline

logger = structlog.get_logger()

router = APIRouter(prefix="/voice", tags=["voice"])

# Initialize Daily room manager
daily_manager = DailyRoomManager(settings.DAILY_API_KEY) if settings.DAILY_API_KEY else None


class PromptTestRequest(BaseModel):
    """Request to test a conversation prompt."""
    customer_id: str
    system_prompt: str
    user_message: str


class PromptTestResponse(BaseModel):
    """Response from prompt testing."""
    system_prompt: str
    user_message: str
    assistant_response: str
    model: str


@router.post("/test-prompt", response_model=PromptTestResponse)
async def test_prompt(
    request: PromptTestRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Test a conversation prompt with Claude.

    This lets you write and test different use case prompts
    before deploying them in live voice calls.

    Args:
        request: Prompt test request with system prompt and user message

    Returns:
        Assistant's response to test the prompt

    Example:
        POST /voice/test-prompt
        {
            "customer_id": "cust_abc123",
            "system_prompt": "You are a helpful assistant for Acme Corp...",
            "user_message": "I need to check my order status"
        }
    """
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.id == request.customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Initialize Anthropic client
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        # Call Claude with the test prompt
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=request.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": request.user_message
                }
            ]
        )

        assistant_response = response.content[0].text

        logger.info(
            "prompt_test_completed",
            customer_id=customer.id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens
        )

        return PromptTestResponse(
            system_prompt=request.system_prompt,
            user_message=request.user_message,
            assistant_response=assistant_response,
            model=response.model
        )

    except Exception as e:
        logger.error(
            "prompt_test_failed",
            customer_id=customer.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test prompt: {str(e)}"
        )


class UseCasePrompt(BaseModel):
    """A use case prompt template."""
    name: str
    description: str
    system_prompt: str
    example_queries: list[str]


@router.get("/example-prompts", response_model=list[UseCasePrompt])
async def get_example_prompts():
    """
    Get example use case prompts to get started.

    Returns:
        List of example prompts for common use cases
    """
    return [
        UseCasePrompt(
            name="Customer Service Agent",
            description="Handle customer inquiries, check order status, process returns",
            system_prompt="""You are a friendly customer service agent for Acme Corporation.

Your capabilities:
- Check order status
- Process returns and refunds
- Answer product questions
- Handle complaints professionally

Guidelines:
- Be empathetic and understanding
- Keep responses concise (this is a voice conversation)
- If you need to transfer to a human, say so clearly
- Always confirm order numbers before proceeding

Example conversation flow:
1. Greet the customer warmly
2. Ask how you can help
3. Gather necessary information (order number, etc.)
4. Provide the requested assistance
5. Ask if there's anything else you can help with""",
            example_queries=[
                "I want to check my order status",
                "I need to return a product",
                "When will my package arrive?",
                "I have a complaint about my recent purchase"
            ]
        ),
        UseCasePrompt(
            name="Appointment Scheduler",
            description="Schedule, reschedule, and cancel appointments",
            system_prompt="""You are an appointment scheduling assistant for Dr. Smith's Medical Practice.

Your capabilities:
- Schedule new appointments
- Reschedule existing appointments
- Cancel appointments
- Check available time slots

Guidelines:
- Confirm patient name and phone number
- Office hours: Monday-Friday, 9 AM - 5 PM
- Appointments are 30 minutes each
- Always read back the scheduled time for confirmation
- Ask about the reason for visit (optional)

When scheduling:
1. Get patient name and contact info
2. Ask for preferred date/time
3. Check availability
4. Confirm the appointment details""",
            example_queries=[
                "I'd like to schedule an appointment",
                "Can I reschedule my appointment for next Tuesday?",
                "I need to cancel my appointment tomorrow",
                "What times are available this week?"
            ]
        ),
        UseCasePrompt(
            name="Restaurant Reservation",
            description="Handle restaurant reservations and table bookings",
            system_prompt="""You are a reservation assistant for La Bella Restaurant.

Your capabilities:
- Take new reservations
- Modify existing reservations
- Cancel reservations
- Answer questions about the menu and hours

Restaurant details:
- Hours: Tuesday-Sunday, 5 PM - 10 PM (Closed Mondays)
- Table sizes: 2, 4, 6, or 8 people
- Accepts reservations up to 30 days in advance

Guidelines:
- Get customer name and phone number
- Ask for party size, date, and preferred time
- Confirm reservation details
- Mention any special requests (birthdays, dietary restrictions)

Conversation flow:
1. Greet warmly
2. Ask for reservation details (date, time, party size)
3. Check availability
4. Get contact information
5. Confirm the booking""",
            example_queries=[
                "I'd like to make a reservation for Saturday night",
                "Table for 4 people at 7 PM",
                "Do you have availability for this Friday?",
                "I need to change my reservation to a different time"
            ]
        ),
        UseCasePrompt(
            name="Lead Qualification",
            description="Qualify sales leads and gather information",
            system_prompt="""You are a sales qualification assistant for TechStart Software.

Your goal is to qualify leads by gathering key information:
1. Company name and size
2. Current pain points or challenges
3. Budget range
4. Decision timeline
5. Decision makers involved

Guidelines:
- Be professional but conversational
- Ask open-ended questions
- Listen actively and acknowledge their needs
- Don't be pushy - build rapport first
- If highly qualified, offer to schedule a demo

Conversation flow:
1. Thank them for their interest
2. Ask about their company and role
3. Understand their current challenges
4. Gauge budget and timeline
5. Determine next steps (demo, follow-up, etc.)""",
            example_queries=[
                "I'm interested in your software",
                "Tell me more about your pricing",
                "We're looking for a solution to manage our team better",
                "Can you schedule a demo?"
            ]
        )
    ]


@router.post("/incoming-call")
async def handle_incoming_call(
    request: Request,
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    SignalWire Primary Script for incoming calls (SWML format).

    Returns SWML using the AI connector to integrate with our voice pipeline.

    Configure this as your SignalWire phone number Primary Script URL:
    https://voicemesh.fly.dev/voice/incoming-call?customer_id=YOUR_CUSTOMER_ID

    Args:
        customer_id: Query parameter to identify which customer owns this number
    """
    logger.info("swml_primary_script_requested", customer_id=customer_id)

    # Verify customer exists
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        logger.error("customer_not_found_in_primary_script", customer_id=customer_id)
        return JSONResponse(
            content={
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "play": {
                                "url": "say:Sorry, this service is not configured. Please contact support."
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
        )

    # Get system prompt from customer or use default
    system_prompt = customer.system_prompt or "You are a helpful AI assistant. Keep your responses brief and conversational since this is a phone call."

    # Return SWML with AI connector
    return JSONResponse(
        content={
            "version": "1.0.0",
            "sections": {
                "main": [
                    {
                        "ai": {
                            "post_prompt_url": f"https://voicemesh.fly.dev/voice/ai-webhook?customer_id={customer_id}",
                            "post_prompt_auth_user": "",
                            "post_prompt_auth_password": "",
                            "params": {
                                "language": customer.default_language or "en-US",
                                "voice": "en-US-Neural2-F"
                            },
                            "prompt": {
                                "text": system_prompt
                            },
                            "SWAIG": {
                                "defaults": {
                                    "web_hook_url": f"https://voicemesh.fly.dev/voice/function-call?customer_id={customer_id}"
                                },
                                "functions": []
                            }
                        }
                    }
                ]
            }
        }
    )


@router.post("/create-session")
async def create_voice_session(
    request: Request,
    customer_id: str,
    call_id: str,
    db: AsyncSession = Depends(get_db),
    from_number: str = "",
    to_number: str = ""
):
    """
    Create a Daily.co session and start Pipecat pipeline for an incoming call.

    This is called by SWML's 'request' directive with call parameters.
    Returns SWML to connect the call to Daily's SIP endpoint.

    Args:
        customer_id: Customer ID from query params
        call_id: SignalWire call ID from SWML variable
        from_number: Caller's phone number
        to_number: Called number
    """
    if not daily_manager:
        logger.error("daily_api_key_not_configured")
        raise HTTPException(status_code=500, detail="Daily.co not configured")

    logger.info(
        "creating_voice_session",
        customer_id=customer_id,
        call_id=call_id,
        from_number=from_number,
        to_number=to_number
    )

    # Verify customer exists
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        logger.error("customer_not_found", customer_id=customer_id)
        return JSONResponse(
            content={
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "play": {
                                "url": "say:Sorry, this service is not configured correctly. Please contact support."
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
        )

    # Create Call record
    call = Call(
        customer_id=customer_id,
        call_sid=call_id,
        from_number=from_number,
        to_number=to_number,
        status="in_progress",
        started_at=None  # Will be set by SQLAlchemy default
    )

    db.add(call)
    await db.commit()
    await db.refresh(call)  # Get the generated ID

    logger.info("call_record_created", call_id=call.id, customer_id=customer_id)

    try:
        # Create Daily.co room for this call
        room = await daily_manager.create_room(call.id, enable_recording=True)

        logger.info(
            "daily_room_created_for_call",
            call_id=call.id,
            room_url=room["url"],
            sip_endpoint=room["sip_endpoint"]
        )

        # Start Pipecat pipeline in background
        # Pipeline will connect to Daily room and process audio through Deepgram + Claude + Cartesia
        asyncio.create_task(
            start_voice_pipeline(
                customer=customer,
                call=call,
                room_url=room["url"],
                room_token=room["token"],
                db=db
            )
        )

        # Return SWML directing SignalWire to connect to Daily's SIP endpoint
        sip_uri = f"sip:{room['sip_endpoint']}@sip.daily.co"

        swml_response = {
            "response": [
                {
                    "play": {
                        "url": "say:Connecting you to our AI assistant."
                    }
                },
                {
                    "connect": {
                        "to": sip_uri
                    }
                }
            ]
        }

        logger.info(
            "swml_response_sent",
            call_id=call.id,
            sip_endpoint=room["sip_endpoint"],
            sip_uri=sip_uri
        )

        # Return SWML as JSON
        return JSONResponse(content=swml_response)

    except Exception as e:
        logger.error(
            "voice_session_creation_failed",
            call_id=call.id,
            error=str(e)
        )

        # Return error SWML response
        return JSONResponse(
            content={
                "response": [
                    {
                        "play": {
                            "url": "say:Sorry, we're experiencing technical difficulties. Please try again later."
                        }
                    },
                    {
                        "hangup": {}
                    }
                ]
            }
        )


async def start_voice_pipeline(
    customer: Customer,
    call: Call,
    room_url: str,
    room_token: str,
    db: AsyncSession
):
    """
    Start the Pipecat voice pipeline for a call.

    This runs in the background and connects to the Daily room.
    Audio flows through: Daily → Deepgram STT → Claude LLM → Cartesia TTS → Daily

    Args:
        customer: Customer making the call
        call: Call record
        room_url: Daily.co room URL
        room_token: Bot token for Daily room
        db: Database session
    """
    try:
        logger.info(
            "starting_voice_pipeline",
            call_id=call.id,
            customer_id=customer.id
        )

        # Create and configure pipeline with customer settings
        # Get voice config from customer or use defaults
        voice_config = customer.voice_config or {}

        pipeline = VoiceMeshPipeline(
            customer=customer,
            deepgram_config={
                "model": "nova-2",
                "language": customer.default_language or "en",
                "smart_format": True,
                "punctuate": True
            },
            cartesia_config={
                "voice_id": voice_config.get("voice_id", "a0e99841-438c-4a64-b679-ae501e7d6091"),  # Default: Barbershop Man
                "speed": voice_config.get("speed", 0.9),  # Slower = more natural
                "emotion": voice_config.get("emotion")
            }
        )

        # Set up pipeline with Daily transport
        await pipeline.setup_pipeline(
            room_url=room_url,
            token=room_token,
            bot_name="VoiceMesh AI"
        )

        # Start pipeline (blocks until call ends)
        await pipeline.start()

        logger.info(
            "voice_pipeline_completed",
            call_id=call.id
        )

        # Update call status
        call.status = "completed"
        await db.commit()

    except Exception as e:
        logger.error(
            "voice_pipeline_failed",
            call_id=call.id,
            error=str(e)
        )

        # Update call status to failed
        call.status = "failed"
        await db.commit()

    finally:
        # Clean up Daily room
        if daily_manager:
            try:
                room_name = f"voicemesh-{call.id}"
                await daily_manager.delete_room(room_name)
            except Exception as e:
                logger.warning(
                    "daily_room_cleanup_failed",
                    call_id=call.id,
                    error=str(e)
                )


@router.post("/process-speech")
async def process_speech(
    request: Request,
    call_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Process speech input from caller and generate AI response.

    This is called by SignalWire after the caller speaks.
    """
    form_data = await request.form()

    speech_result = form_data.get("SpeechResult", "")
    confidence = form_data.get("Confidence", "0")

    logger.info(
        "speech_received",
        call_id=call_id,
        speech=speech_result,
        confidence=confidence
    )

    # Get the call record
    result = await db.execute(
        select(Call).where(Call.id == call_id)
    )
    call = result.scalar_one_or_none()

    if not call:
        logger.error("call_not_found", call_id=call_id)
        return JSONResponse(
            content={
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "play": {
                                "url": "say:Sorry, there was an error. Goodbye."
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
        )

    # Update call transcript
    if call.transcript:
        call.transcript += f"\nUser: {speech_result}"
    else:
        call.transcript = f"User: {speech_result}"

    # Generate AI response using Claude
    # For now, use a simple system prompt
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        ai_response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=256,  # Keep responses concise for voice
            system="You are a helpful AI assistant. Keep your responses brief and conversational since this is a phone call.",
            messages=[
                {
                    "role": "user",
                    "content": speech_result
                }
            ]
        )

        assistant_text = ai_response.content[0].text

        # Update transcript with assistant response
        call.transcript += f"\nAssistant: {assistant_text}"

        # Track token usage for cost calculation
        input_tokens = ai_response.usage.input_tokens
        output_tokens = ai_response.usage.output_tokens

        # Claude 3.5 Sonnet pricing: $3/MTok input, $15/MTok output
        cost_llm = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

        if call.cost_llm:
            call.cost_llm += cost_llm
        else:
            call.cost_llm = cost_llm

        await db.commit()

        logger.info(
            "ai_response_generated",
            call_id=call_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost_llm
        )

        # Create SWML response with AI's answer
        return JSONResponse(
            content={
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "play": {
                                "url": f"say:{assistant_text}"
                            }
                        },
                        {
                            "prompt": {
                                "play": "say:",
                                "max_digits": 0,
                                "speech_timeout": 3000,
                                "action_url": f"/voice/process-speech?call_id={call.id}"
                            }
                        },
                        {
                            "play": {
                                "url": "say:Thank you for calling. Goodbye!"
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
        )

    except Exception as e:
        logger.error(
            "ai_response_failed",
            call_id=call_id,
            error=str(e)
        )

        return JSONResponse(
            content={
                "version": "1.0.0",
                "sections": {
                    "main": [
                        {
                            "play": {
                                "url": "say:Sorry, I encountered an error. Please try again later."
                            }
                        },
                        {
                            "hangup": {}
                        }
                    ]
                }
            }
        )
