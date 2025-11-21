"""Voice configuration endpoints for Deepgram and Cartesia settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import structlog

from src.api.database import get_db
from src.platform.cartesia_tts import CARTESIA_VOICES, CARTESIA_EMOTIONS

logger = structlog.get_logger()

router = APIRouter(prefix="/voice/config", tags=["voice-config"])


# ==================== Deepgram Configuration ====================

class DeepgramModels(BaseModel):
    """Available Deepgram models."""
    models: List[dict] = [
        {
            "id": "nova-2",
            "name": "Nova 2",
            "description": "Latest and most accurate model, best for production",
            "use_cases": ["customer service", "transcription", "general"],
            "cost_per_hour": "$0.59"
        },
        {
            "id": "nova",
            "name": "Nova",
            "description": "Previous generation, still very accurate",
            "use_cases": ["general transcription", "cost-conscious"],
            "cost_per_hour": "$0.43"
        },
        {
            "id": "enhanced",
            "name": "Enhanced",
            "description": "Enhanced model for difficult audio",
            "use_cases": ["noisy environments", "accents"],
            "cost_per_hour": "$0.55"
        },
        {
            "id": "base",
            "name": "Base",
            "description": "Most cost-effective option",
            "use_cases": ["high-volume", "budget-constrained"],
            "cost_per_hour": "$0.25"
        }
    ]


class DeepgramConfig(BaseModel):
    """Deepgram STT configuration options."""
    model: str = Field(
        default="nova-2",
        description="Model to use: nova-2, nova, enhanced, or base"
    )
    language: str = Field(
        default="en",
        description="Language code: en, es, fr, de, etc."
    )
    smart_format: bool = Field(
        default=True,
        description="Enable smart formatting (dates, times, currency)"
    )
    punctuate: bool = Field(
        default=True,
        description="Add punctuation to transcripts"
    )
    profanity_filter: bool = Field(
        default=False,
        description="Filter profanity from transcripts"
    )
    keywords: List[str] = Field(
        default=[],
        description="Keywords to boost recognition (e.g., product names, brands)"
    )
    diarize: bool = Field(
        default=False,
        description="Identify different speakers"
    )


@router.get("/deepgram/models", response_model=DeepgramModels)
async def get_deepgram_models():
    """
    Get available Deepgram STT models.

    Returns:
        List of available models with details
    """
    return DeepgramModels()


@router.get("/deepgram/languages")
async def get_deepgram_languages():
    """
    Get supported languages for Deepgram STT.

    Returns:
        List of supported language codes
    """
    return {
        "languages": [
            {"code": "en", "name": "English", "variants": ["en-US", "en-GB", "en-AU", "en-IN"]},
            {"code": "es", "name": "Spanish", "variants": ["es-ES", "es-419"]},
            {"code": "fr", "name": "French", "variants": ["fr-FR", "fr-CA"]},
            {"code": "de", "name": "German", "variants": ["de-DE"]},
            {"code": "pt", "name": "Portuguese", "variants": ["pt-BR", "pt-PT"]},
            {"code": "nl", "name": "Dutch", "variants": ["nl-NL"]},
            {"code": "hi", "name": "Hindi", "variants": ["hi-IN"]},
            {"code": "ja", "name": "Japanese", "variants": ["ja-JP"]},
            {"code": "zh", "name": "Chinese", "variants": ["zh-CN", "zh-TW"]},
            {"code": "ko", "name": "Korean", "variants": ["ko-KR"]},
            {"code": "it", "name": "Italian", "variants": ["it-IT"]},
            {"code": "ru", "name": "Russian", "variants": ["ru-RU"]},
            {"code": "tr", "name": "Turkish", "variants": ["tr-TR"]},
            {"code": "id", "name": "Indonesian", "variants": ["id-ID"]},
            {"code": "uk", "name": "Ukrainian", "variants": ["uk-UA"]},
        ]
    }


# ==================== Cartesia Configuration ====================

class CartesiaVoice(BaseModel):
    """Cartesia voice option."""
    id: str
    name: str
    description: str
    sample_url: Optional[str] = None


class CartesiaVoicesResponse(BaseModel):
    """Available Cartesia voices."""
    voices: List[CartesiaVoice]


class CartesiaConfig(BaseModel):
    """Cartesia TTS configuration options."""
    voice_id: str = Field(
        default="barbershop_man",
        description="Voice ID or name from available voices"
    )
    model_id: str = Field(
        default="sonic-english",
        description="sonic-english (faster) or sonic-multilingual"
    )
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Speech speed: 0.5 (slow) to 2.0 (fast)"
    )
    emotion: Optional[str] = Field(
        default=None,
        description="Emotion: neutral, happy, sad, angry, curious, surprised, calm"
    )


@router.get("/cartesia/voices", response_model=CartesiaVoicesResponse)
async def get_cartesia_voices():
    """
    Get available Cartesia TTS voices.

    Returns:
        List of available voices with details
    """
    voices = [
        CartesiaVoice(
            id=CARTESIA_VOICES["barbershop_man"],
            name="Barbershop Man",
            description="Warm, friendly male voice - great for customer service"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["helpful_woman"],
            name="Helpful Woman",
            description="Professional female voice - ideal for support and guidance"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["salesman"],
            name="Salesman",
            description="Energetic male voice - perfect for sales and enthusiasm"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["newscaster"],
            name="Newscaster",
            description="Clear, authoritative voice - best for information delivery"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["friendly_sidekick"],
            name="Friendly Sidekick",
            description="Casual, upbeat voice - great for casual conversations"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["customer_support"],
            name="Customer Support",
            description="Empathetic, helpful voice - designed for support interactions"
        ),
        CartesiaVoice(
            id=CARTESIA_VOICES["meditation"],
            name="Meditation",
            description="Calm, soothing voice - perfect for relaxation and guidance"
        ),
    ]

    return CartesiaVoicesResponse(voices=voices)


@router.get("/cartesia/emotions")
async def get_cartesia_emotions():
    """
    Get available emotions for Cartesia TTS.

    Returns:
        List of available emotions
    """
    return {
        "emotions": [
            {"id": "neutral", "name": "Neutral", "description": "Standard, balanced tone"},
            {"id": "happy", "name": "Happy", "description": "Cheerful and upbeat"},
            {"id": "sad", "name": "Sad", "description": "Empathetic and understanding"},
            {"id": "angry", "name": "Angry", "description": "Firm and assertive"},
            {"id": "curious", "name": "Curious", "description": "Engaged and interested"},
            {"id": "surprised", "name": "Surprised", "description": "Excited and amazed"},
            {"id": "calm", "name": "Calm", "description": "Peaceful and reassuring"},
        ]
    }


@router.get("/cartesia/models")
async def get_cartesia_models():
    """
    Get available Cartesia TTS models.

    Returns:
        List of available models
    """
    return {
        "models": [
            {
                "id": "sonic-english",
                "name": "Sonic English",
                "description": "Optimized for English, fastest latency (~200ms)",
                "languages": ["en"],
                "latency": "~200ms"
            },
            {
                "id": "sonic-multilingual",
                "name": "Sonic Multilingual",
                "description": "Supports 25+ languages, slightly higher latency (~250ms)",
                "languages": ["en", "es", "fr", "de", "pt", "it", "nl", "pl", "tr", "ru", "zh", "ja", "ko", "hi", "ar"],
                "latency": "~250ms"
            }
        ]
    }


# ==================== Combined Configuration ====================

class VoiceConfiguration(BaseModel):
    """Complete voice configuration for a call."""
    deepgram: DeepgramConfig = DeepgramConfig()
    cartesia: CartesiaConfig = CartesiaConfig()


class VoiceConfigurationExample(BaseModel):
    """Example voice configuration for different use cases."""
    name: str
    description: str
    deepgram: DeepgramConfig
    cartesia: CartesiaConfig


@router.get("/examples", response_model=List[VoiceConfigurationExample])
async def get_voice_config_examples():
    """
    Get example voice configurations for common use cases.

    Returns:
        List of example configurations
    """
    return [
        VoiceConfigurationExample(
            name="Customer Service (US English)",
            description="Warm, professional voice with smart formatting",
            deepgram=DeepgramConfig(
                model="nova-2",
                language="en-US",
                smart_format=True,
                punctuate=True,
                keywords=["order number", "shipping", "refund", "support"]
            ),
            cartesia=CartesiaConfig(
                voice_id="helpful_woman",
                model_id="sonic-english",
                speed=0.95,
                emotion="neutral"
            )
        ),
        VoiceConfigurationExample(
            name="Sales Outreach",
            description="Energetic, engaging voice for sales calls",
            deepgram=DeepgramConfig(
                model="nova-2",
                language="en",
                smart_format=True,
                punctuate=True
            ),
            cartesia=CartesiaConfig(
                voice_id="salesman",
                model_id="sonic-english",
                speed=1.1,
                emotion="happy"
            )
        ),
        VoiceConfigurationExample(
            name="Medical Appointment",
            description="Calm, empathetic voice for healthcare",
            deepgram=DeepgramConfig(
                model="enhanced",
                language="en",
                smart_format=True,
                punctuate=True,
                keywords=["appointment", "doctor", "patient", "insurance"]
            ),
            cartesia=CartesiaConfig(
                voice_id="customer_support",
                model_id="sonic-english",
                speed=0.9,
                emotion="calm"
            )
        ),
        VoiceConfigurationExample(
            name="Restaurant Reservations",
            description="Friendly, casual voice for bookings",
            deepgram=DeepgramConfig(
                model="nova-2",
                language="en",
                smart_format=True,
                punctuate=True,
                keywords=["reservation", "table", "party size", "time"]
            ),
            cartesia=CartesiaConfig(
                voice_id="friendly_sidekick",
                model_id="sonic-english",
                speed=1.0,
                emotion="happy"
            )
        ),
        VoiceConfigurationExample(
            name="Spanish Customer Support",
            description="Professional Spanish language support",
            deepgram=DeepgramConfig(
                model="nova-2",
                language="es",
                smart_format=True,
                punctuate=True
            ),
            cartesia=CartesiaConfig(
                voice_id="helpful_woman",
                model_id="sonic-multilingual",
                speed=0.95,
                emotion="neutral"
            )
        ),
    ]


@router.post("/validate", response_model=dict)
async def validate_voice_config(config: VoiceConfiguration):
    """
    Validate a voice configuration.

    Args:
        config: Voice configuration to validate

    Returns:
        Validation result with any warnings or errors
    """
    warnings = []
    errors = []

    # Validate Deepgram config
    valid_models = ["nova-2", "nova", "enhanced", "base"]
    if config.deepgram.model not in valid_models:
        errors.append(f"Invalid Deepgram model. Must be one of: {', '.join(valid_models)}")

    # Validate Cartesia config
    if config.cartesia.speed < 0.5 or config.cartesia.speed > 2.0:
        errors.append("Cartesia speed must be between 0.5 and 2.0")

    if config.cartesia.emotion and config.cartesia.emotion not in CARTESIA_EMOTIONS:
        errors.append(f"Invalid emotion. Must be one of: {', '.join(CARTESIA_EMOTIONS)}")

    # Add warnings
    if config.deepgram.model == "base":
        warnings.append("Base model has lower accuracy. Consider 'nova-2' for better results.")

    if config.cartesia.speed > 1.3:
        warnings.append("Speed > 1.3 may reduce intelligibility for some listeners")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "estimated_cost_per_minute": {
            "deepgram_stt": 0.0098 if config.deepgram.model == "nova-2" else 0.0042,
            "cartesia_tts": 0.015,
            "anthropic_llm": 0.045,
            "total": 0.0698 if config.deepgram.model == "nova-2" else 0.0612
        }
    }
