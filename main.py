import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_AGENTS_URL = "https://api.deepgram.com/v1/agents"
DEEPGRAM_SESSIONS_URL = "https://api.deepgram.com/v1/voice/sessions"

if not DEEPGRAM_API_KEY:
    print("WARNING: DEEPGRAM_API_KEY not set")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not set (required for agent creation)")

app = FastAPI(
    title="VoiceMesh - Deepgram Voice Agent",
    description="Backend for creating and managing Deepgram Voice Agents",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateAgentRequest(BaseModel):
    """Request body for creating a complete voice agent"""
    agent_name: str = Field(default="customer_support_agent", description="Name/tag for the agent")
    system_prompt: str = Field(
        default="You are a friendly and helpful customer support agent. Speak in a warm, polite manner and assist callers with their questions.",
        description="System prompt for the LLM"
    )
    greeting: str = Field(
        default="Hello! How can I help you today?",
        description="Initial greeting when call starts"
    )
    voice_model: str = Field(default="aura-2-andromeda-en", description="Deepgram TTS voice model")
    llm_model: str = Field(default="claude-4-5-haiku-latest", description="Anthropic Claude model")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="LLM temperature")
    stt_model: str = Field(default="flux-general-en", description="Deepgram STT model")
    language: str = Field(default="en", description="Agent language")


class CreateAgentResponse(BaseModel):
    """Response after creating an agent"""
    agent_id: str
    message: str


class StartSessionRequest(BaseModel):
    """Request body for starting a session with an existing agent"""
    agent_id: str = Field(description="The agent ID to create a session for")
    metadata: Optional[dict] = Field(default=None, description="Optional session metadata")


class StartSessionResponse(BaseModel):
    """Response containing session details"""
    session_id: str
    ws_url: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "VoiceMesh",
        "version": "2.0.0",
        "description": "Deepgram Voice Agent Backend",
        "endpoints": {
            "health": "GET /health",
            "create_agent": "POST /create-agent",
            "start_session": "POST /start-session",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    has_deepgram_key = bool(DEEPGRAM_API_KEY)
    has_anthropic_key = bool(ANTHROPIC_API_KEY)

    return {
        "status": "ok" if has_deepgram_key else "misconfigured",
        "deepgram_api_key_set": has_deepgram_key,
        "anthropic_api_key_set": has_anthropic_key,
        "message": "All keys configured" if (has_deepgram_key and has_anthropic_key) else "Missing API keys"
    }


@app.post("/create-agent", response_model=CreateAgentResponse)
async def create_agent(body: CreateAgentRequest):
    """
    Creates a complete Deepgram Voice Agent with STT, LLM, and TTS configuration.

    This creates a full agent configuration based on the setup from the PDF:
    - STT: Deepgram (flux-general-en)
    - LLM: Anthropic Claude (claude-4-5-haiku-latest)
    - TTS: Deepgram Aura (aura-2-andromeda-en)

    Returns the agent_id which can be used to create sessions.
    """
    if not DEEPGRAM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: DEEPGRAM_API_KEY not set"
        )

    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: ANTHROPIC_API_KEY not set (required for agent creation)"
        )

    # Build the agent configuration (from the PDF)
    agent_config = {
        "type": "Settings",
        "tags": ["voicemesh", body.agent_name],
        "audio": {
            "input": {
                "encoding": "linear16",
                "sample_rate": 24000
            },
            "output": {
                "encoding": "linear16",
                "sample_rate": 24000,
                "container": "none"
            }
        },
        "agent": {
            "language": body.language,
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": body.stt_model,
                    "smart_format": False
                }
            },
            "think": {
                "provider": {
                    "type": "anthropic",
                    "model": body.llm_model,
                    "temperature": body.llm_temperature
                },
                "endpoint": {
                    "url": "https://api.anthropic.com/v1/complete",
                    "headers": {
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01"
                    }
                },
                "prompt": body.system_prompt
            },
            "speak": {
                "provider": {
                    "type": "deepgram",
                    "model": body.voice_model
                }
            },
            "greeting": body.greeting
        }
    }

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                DEEPGRAM_AGENTS_URL,
                json=agent_config,
                headers=headers,
            )

        if resp.status_code not in [200, 201]:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Deepgram API error: {resp.text}"
            )

        data = resp.json()
        agent_id = data.get("agent_id") or data.get("id")

        if not agent_id:
            raise HTTPException(
                status_code=500,
                detail=f"Agent created but no agent_id returned. Response: {data}"
            )

        return CreateAgentResponse(
            agent_id=agent_id,
            message=f"Agent '{body.agent_name}' created successfully"
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout connecting to Deepgram API"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@app.post("/start-session", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest):
    """
    Creates a session for an existing agent and returns the WebSocket URL.

    The client can then:
    1. Connect to the ws_url via WebSocket
    2. Stream audio to/from the Deepgram Voice Agent
    """
    if not DEEPGRAM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: DEEPGRAM_API_KEY not set"
        )

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    payload = {"agent_id": body.agent_id}

    if body.metadata:
        payload["metadata"] = body.metadata

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                DEEPGRAM_SESSIONS_URL,
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Deepgram API error: {resp.text}"
            )

        data = resp.json()
        return StartSessionResponse(
            session_id=data["session_id"],
            ws_url=data["ws_url"],
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout connecting to Deepgram API"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
