"""Voice AI testing and call management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from twilio.twiml.voice_response import VoiceResponse, Gather, Say

from src.api.database import get_db
from src.api.models import Customer, Call
from anthropic import Anthropic

from src.api.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/voice", tags=["voice"])


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
    SignalWire webhook for incoming voice calls.

    When someone calls your SignalWire number, this endpoint:
    1. Receives call metadata from SignalWire
    2. Creates a Call record in the database
    3. Returns TwiML to greet caller and start AI conversation

    Configure this as your SignalWire phone number webhook:
    https://your-app.fly.dev/voice/incoming-call?customer_id=YOUR_CUSTOMER_ID

    Args:
        customer_id: Query parameter to identify which customer owns this number
    """
    # Get call parameters from SignalWire
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    call_status = form_data.get("CallStatus")

    logger.info(
        "incoming_call_received",
        customer_id=customer_id,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        call_status=call_status
    )

    # Verify customer exists
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        logger.error("customer_not_found", customer_id=customer_id)
        raise HTTPException(status_code=404, detail="Customer not found")

    # Create Call record
    call = Call(
        customer_id=customer_id,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        status="in_progress",
        started_at=None  # Will be set by SQLAlchemy default
    )

    db.add(call)
    await db.commit()

    logger.info("call_record_created", call_id=call.id, customer_id=customer_id)

    # Create VoiceResponse with AI greeting
    response = VoiceResponse()

    # Greet the caller
    response.say(
        "Hello! Welcome to Voice Mesh. I'm your A I assistant. How can I help you today?",
        voice="Polly.Joanna",
        language="en-US"
    )

    # Gather speech input
    gather = Gather(
        input="speech",
        action=f"/voice/process-speech?call_id={call.id}",
        method="POST",
        speech_timeout="auto",
        language="en-US"
    )

    response.append(gather)

    # If no input, say goodbye
    response.say("I didn't hear anything. Goodbye!")
    response.hangup()

    # Return TwiML as XML
    return Response(
        content=str(response),
        media_type="application/xml"
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
        response = VoiceResponse()
        response.say("Sorry, there was an error. Goodbye.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

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

        # Create response with AI's answer
        response = VoiceResponse()
        response.say(
            assistant_text,
            voice="Polly.Joanna",
            language="en-US"
        )

        # Gather next input
        gather = Gather(
            input="speech",
            action=f"/voice/process-speech?call_id={call.id}",
            method="POST",
            speech_timeout="auto",
            language="en-US"
        )

        response.append(gather)

        # If no more input, end call
        response.say("Thank you for calling. Goodbye!")
        response.hangup()

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(
            "ai_response_failed",
            call_id=call_id,
            error=str(e)
        )

        response = VoiceResponse()
        response.say("Sorry, I encountered an error. Please try again later.")
        response.hangup()

        return Response(content=str(response), media_type="application/xml")
