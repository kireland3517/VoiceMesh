"""Voice pipeline using Pipecat for real-time voice AI conversations."""

import asyncio
from typing import Optional, Dict, Any
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.transports.services.daily import DailyTransport, DailyParams
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
import structlog

# Note: Silero VAD disabled for faster deployment
# To enable: pip install pipecat-ai[silero] and uncomment below
# from pipecat.vad.silero import SileroVADAnalyzer

from src.platform.cartesia_tts import CartesiaTTSService
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

    def __init__(
        self,
        customer: Customer,
        deepgram_config: Optional[Dict[str, Any]] = None,
        cartesia_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize voice pipeline for a customer.

        Args:
            customer: Customer making the call
            deepgram_config: Deepgram STT configuration options
                - model: "nova-2", "nova", "enhanced", "base" (default: "nova-2")
                - language: "en", "es", "fr", etc. (default: "en")
                - smart_format: Enable smart formatting (default: True)
                - punctuate: Add punctuation (default: True)
                - profanity_filter: Filter profanity (default: False)
                - keywords: List of keywords to boost recognition
            cartesia_config: Cartesia TTS configuration options
                - voice_id: Voice ID or name (default: "barbershop_man")
                - model_id: "sonic-english" or "sonic-multilingual" (default: "sonic-english")
                - speed: Speech speed 0.5-2.0 (default: 1.0)
                - emotion: "neutral", "happy", "sad", "angry", etc. (default: None)
        """
        self.customer = customer
        self.pipeline: Optional[Pipeline] = None
        self.runner: Optional[PipelineRunner] = None
        self.task: Optional[PipelineTask] = None

        # Deepgram configuration
        self.deepgram_config = deepgram_config or {}
        self.deepgram_model = self.deepgram_config.get("model", "nova-2")
        self.deepgram_language = self.deepgram_config.get("language", "en")
        self.deepgram_smart_format = self.deepgram_config.get("smart_format", True)
        self.deepgram_punctuate = self.deepgram_config.get("punctuate", True)
        self.deepgram_profanity_filter = self.deepgram_config.get("profanity_filter", False)
        self.deepgram_keywords = self.deepgram_config.get("keywords", [])

        # Cartesia configuration
        self.cartesia_config = cartesia_config or {}
        self.cartesia_voice_id = self.cartesia_config.get("voice_id", "a0e99841-438c-4a64-b679-ae501e7d6091")  # Default: Barbershop Man
        self.cartesia_model = self.cartesia_config.get("model_id", "sonic-english")
        self.cartesia_speed = self.cartesia_config.get("speed", None)
        self.cartesia_emotion = self.cartesia_config.get("emotion", None)

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

        # 1. Transport (Daily.co with container-friendly configuration)
        # Note: VAD disabled for now (Silero requires heavy ML dependencies)
        transport = DailyTransport(
            room_url,
            token,
            bot_name,
            DailyParams(
                audio_out_enabled=True,
                audio_in_enabled=True,
                vad_enabled=False,  # Disabled for faster deployment
                transcription_enabled=False,  # We use Deepgram
                camera_out_enabled=False,  # No video needed for voice calls
            )
        )

        # 3. Speech-to-Text (Deepgram with custom configuration)
        stt_params = {
            "api_key": settings.DEEPGRAM_API_KEY,
            "language": self.deepgram_language,
        }

        # Add optional Deepgram parameters
        if self.deepgram_model:
            stt_params["model"] = self.deepgram_model
        if self.deepgram_smart_format:
            stt_params["smart_format"] = True
        if self.deepgram_punctuate:
            stt_params["punctuate"] = True
        if self.deepgram_profanity_filter:
            stt_params["profanity_filter"] = True
        if self.deepgram_keywords:
            stt_params["keywords"] = self.deepgram_keywords

        stt_service = DeepgramSTTService(**stt_params)

        # 4. LLM (Claude via Anthropic)
        llm_service = AnthropicLLMService(
            api_key=settings.ANTHROPIC_API_KEY,
            model="claude-3-5-sonnet-20241022",
            system=self.get_system_prompt()
        )

        # 5. Text-to-Speech (Custom HTTP-based Cartesia service)
        # Uses HTTP streaming instead of WebSocket for better reliability
        logger.info("creating_cartesia_tts_service", customer_id=self.customer.id)
        tts_service = CartesiaTTSService(
            api_key=settings.CARTESIA_API_KEY,
            voice_id=self.cartesia_voice_id,
            model_id=self.cartesia_model,
            language=self.deepgram_language,
            speed=self.cartesia_speed or 1.0,
            emotion=self.cartesia_emotion,
            sample_rate=16000
        )

        # 6. Build the pipeline
        self.pipeline = Pipeline([
            transport.input(),
            stt_service,
            llm_service,
            tts_service,
            transport.output()
        ])

        # Create simple pipeline task
        self.task = PipelineTask(self.pipeline)

        # Create runner
        self.runner = PipelineRunner()

        logger.info(
            "voice_pipeline_setup_complete",
            customer_id=self.customer.id
        )

    async def start(self):
        """Start the voice pipeline with error handling for failures."""
        if not self.runner or not self.task:
            raise RuntimeError("Pipeline not set up. Call setup_pipeline() first.")

        logger.info("starting_voice_pipeline", customer_id=self.customer.id)
        
        try:
            await self.runner.run(self.task)
        except Exception as e:
            logger.error(
                "voice_pipeline_runtime_error",
                customer_id=self.customer.id,
                error_type=type(e).__name__,
                message=str(e)
            )
            # Don't re-raise to prevent server crashes
        finally:
            logger.info(
                "voice_pipeline_stopped",
                customer_id=self.customer.id
            )

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
        # Use customer's custom system prompt if configured
        system_prompt = getattr(self.customer, 'system_prompt', None)
        if system_prompt:
            return system_prompt

        # Otherwise, use default prompt
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