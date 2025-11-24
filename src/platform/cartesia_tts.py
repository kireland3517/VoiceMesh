"""Custom Cartesia TTS service for Pipecat pipeline."""

import asyncio
import aiohttp
from typing import AsyncGenerator, Optional
from pipecat.frames.frames import Frame, AudioRawFrame, ErrorFrame
from pipecat.processors.frame_processor import FrameProcessor
import structlog

logger = structlog.get_logger()


class CartesiaTTSService(FrameProcessor):
    """
    Cartesia Text-to-Speech service for Pipecat.

    Uses Cartesia's low-latency, cost-effective TTS API.

    Pricing: ~$0.000025/char = ~$0.125/min of speech
    Latency: ~200-300ms (much lower than ElevenLabs)

    Features:
    - Multiple voice options
    - Emotion control (happy, sad, angry, neutral)
    - Speed control (0.5x to 2.0x)
    - Language support
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = "a0e99841-438c-4a64-b679-ae501e7d6091",  # Barbershop Man (default)
        model_id: str = "sonic-english",
        language: str = "en",
        speed: float = 1.0,
        emotion: Optional[str] = None,
        sample_rate: int = 16000,
        **kwargs
    ):
        """
        Initialize Cartesia TTS service.

        Args:
            api_key: Cartesia API key
            voice_id: Voice ID to use (default: Barbershop Man)
            model_id: Model to use (sonic-english, sonic-multilingual)
            language: Language code (en, es, fr, de, etc.)
            speed: Speech speed (0.5 to 2.0)
            emotion: Optional emotion (happy, sad, angry, neutral)
            sample_rate: Audio sample rate in Hz
        """
        super().__init__(**kwargs)

        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.language = language
        self.speed = speed
        self.emotion = emotion
        self.sample_rate = sample_rate

        self.base_url = "https://api.cartesia.ai/v1"
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self, frame):
        """Start the service and create HTTP session."""
        self._session = aiohttp.ClientSession(
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
        )

    async def stop(self, frame):
        """Stop the service and close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def process_frame(self, frame: Frame, direction) -> AsyncGenerator[Frame, None]:
        """Process frames - convert text frames to audio frames."""
        # Only process text frames for TTS
        if hasattr(frame, 'text') and frame.text:
            async for audio_frame in self.run_tts(frame.text):
                yield audio_frame
        else:
            # Pass through other frames unchanged
            yield frame

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """
        Convert text to speech using Cartesia.

        Args:
            text: Text to convert to speech

        Yields:
            AudioRawFrame objects containing audio data
        """
        if not self._session:
            logger.error("cartesia_session_not_initialized")
            yield ErrorFrame("Cartesia session not initialized")
            return

        logger.info(
            "cartesia_tts_request",
            text_length=len(text),
            voice_id=self.voice_id,
            model_id=self.model_id
        )

        try:
            # Prepare request payload
            payload = {
                "model_id": self.model_id,
                "transcript": text,
                "voice": {
                    "mode": "id",
                    "id": self.voice_id
                },
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": self.sample_rate
                },
                "language": self.language
            }

            # Add optional parameters
            if self.speed != 1.0:
                payload["voice"]["speed"] = self.speed

            if self.emotion:
                payload["voice"]["emotion"] = self.emotion

            # Make streaming request to Cartesia
            async with self._session.post(
                f"{self.base_url}/tts/bytes",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "cartesia_tts_error",
                        status=response.status,
                        error=error_text
                    )
                    yield ErrorFrame(f"Cartesia TTS error: {error_text}")
                    return

                # Stream audio chunks
                chunk_count = 0
                async for chunk in response.content.iter_any():
                    if chunk:
                        chunk_count += 1
                        # Yield audio frame
                        yield AudioRawFrame(
                            audio=chunk,
                            sample_rate=self.sample_rate,
                            num_channels=1
                        )

                logger.info(
                    "cartesia_tts_complete",
                    text_length=len(text),
                    chunk_count=chunk_count
                )

        except Exception as e:
            logger.error(
                "cartesia_tts_exception",
                error=str(e),
                text_length=len(text)
            )
            yield ErrorFrame(f"Cartesia TTS exception: {str(e)}")


# Popular Cartesia voice IDs
CARTESIA_VOICES = {
    "barbershop_man": "a0e99841-438c-4a64-b679-ae501e7d6091",  # Warm, friendly male
    "helpful_woman": "b7d50908-b17c-442d-ad8d-810c63997ed9",  # Professional female
    "salesman": "71a7ad14-091c-4e8e-a314-022ece01c121",  # Energetic male
    "newscaster": "d46abd1d-2d02-43e8-819f-51fb652c1c61",  # Clear, authoritative
    "friendly_sidekick": "41534e16-2966-4c6b-9670-111411def906",  # Casual, upbeat
    "customer_support": "87748186-23bb-4158-a1eb-332911b0b708",  # Empathetic, helpful
    "meditation": "58d6d48c-27e6-4e1e-9e3d-6fbdc3876174",  # Calm, soothing
}


# Supported emotions
CARTESIA_EMOTIONS = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "curious",
    "surprised",
    "calm"
]
