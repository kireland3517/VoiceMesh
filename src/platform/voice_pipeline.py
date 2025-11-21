"""Voice pipeline using Pipecat for real-time voice AI conversations."""

import asyncio
from typing import Optional
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.transports.services.daily import DailyTransport, DailyParams
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
import structlog

from src.api.config import settings
from src.api.models import Customer, Function

logger = structlog.get_logger()


class VoiceMeshPipeline:
    """
    VoiceMesh voice pipeline orchestrator.

    Manages the flow of:
    1. Audio input → Deepgram STT → Text
    2. Text → Claude LLM → Response
    3. Response → Cartesia TTS → Audio output
    4. Function calling → MCP execution
    """

    def __init__(self, customer: Customer):
        """
        Initialize voice pipeline for a customer.

        Args:
            customer: Customer making the call
        """
        self.customer = customer
        self.pipeline: Optional[Pipeline] = None
        self.runner: Optional[PipelineRunner] = None

    async def setup_pipeline(
        self,
        room_url: str,
        token: str,
        bot_name: str = "VoiceMesh Assistant"
    ):
        """
        Set up the Pipecat pipeline with all services.

        Args:
            room_url: Daily.co room URL for the call
            token: Daily.co access token
            bot_name: Name for the AI assistant
        """
        logger.info(
            "setting_up_voice_pipeline",
            customer_id=self.customer.id,
            room_url=room_url
        )

        # 1. Transport (Daily.co for now, will add SignalWire)
        transport = DailyTransport(
            room_url,
            token,
            bot_name,
            DailyParams(
                audio_out_enabled=True,
                audio_in_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                transcription_enabled=False  # We use Deepgram
            )
        )

        # 2. Speech-to-Text (Deepgram)
        stt_service = DeepgramSTTService(
            api_key=settings.DEEPGRAM_API_KEY,
            language="en"
        )

        # 3. LLM (Claude via Anthropic)
        llm_service = AnthropicLLMService(
            api_key=settings.ANTHROPIC_API_KEY,
            model="claude-3-5-sonnet-20241022"
        )

        # 4. Text-to-Speech (Cartesia - will implement custom service)
        # For now, we'll use a placeholder
        # tts_service = CartesiaTTSService(api_key=settings.CARTESIA_API_KEY)

        # 5. Build the pipeline
        # self.pipeline = Pipeline([
        #     transport.input(),
        #     stt_service,
        #     llm_service,
        #     tts_service,
        #     transport.output()
        # ])

        # Create pipeline task
        task = PipelineTask(
            self.pipeline,
            PipelineParams(
                allow_interruptions=True,
                enable_metrics=True
            )
        )

        # Create runner
        self.runner = PipelineRunner()

        logger.info(
            "voice_pipeline_setup_complete",
            customer_id=self.customer.id
        )

    async def start(self):
        """Start the voice pipeline."""
        if not self.runner:
            raise RuntimeError("Pipeline not set up. Call setup_pipeline() first.")

        logger.info("starting_voice_pipeline", customer_id=self.customer.id)
        await self.runner.run()

    async def stop(self):
        """Stop the voice pipeline."""
        if self.runner:
            logger.info("stopping_voice_pipeline", customer_id=self.customer.id)
            # Send end frame to gracefully stop
            # await self.pipeline.queue_frames([EndFrame()])

    def get_system_prompt(self) -> str:
        """
        Generate system prompt for the LLM based on customer configuration.

        Returns:
            System prompt for Claude
        """
        prompt = f"""You are a helpful AI assistant for {self.customer.name}.

You have access to the following custom functions:
"""

        # Add customer's registered functions
        if self.customer.functions:
            for func in self.customer.functions:
                if func.is_active:
                    prompt += f"\n- {func.name}: {func.description}"
        else:
            prompt += "\n(No custom functions registered yet)"

        prompt += """

When a user asks you to perform an action that matches one of these functions,
call the appropriate function with the necessary parameters.

Be conversational, helpful, and concise in your responses since this is a voice conversation.
"""

        return prompt


async def create_voice_call(
    customer: Customer,
    phone_number: str,
    context: Optional[dict] = None
):
    """
    Create and start a voice call for a customer.

    Args:
        customer: Customer making the call
        phone_number: Phone number to call
        context: Optional context data for the conversation

    Returns:
        Call record
    """
    logger.info(
        "creating_voice_call",
        customer_id=customer.id,
        phone_number=phone_number
    )

    # For now, this is a placeholder
    # We'll implement the full SignalWire integration later

    # TODO:
    # 1. Create Daily.co room
    # 2. Dial phone number via SignalWire
    # 3. Bridge SignalWire call to Daily.co room
    # 4. Start voice pipeline

    return {
        "status": "initiated",
        "message": "Voice call functionality coming soon"
    }
