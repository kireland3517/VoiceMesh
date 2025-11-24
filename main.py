import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Deepgram configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_AGENT_ID = os.getenv("DEEPGRAM_AGENT_ID")
DEEPGRAM_VOICE_SESSION_URL = "https://api.deepgram.com/v1/voice/sessions"

if not DEEPGRAM_API_KEY or not DEEPGRAM_AGENT_ID:
    print("WARNING: DEEPGRAM_API_KEY or DEEPGRAM_AGENT_ID not set")
    print("Please set these environment variables before starting the server")

app = FastAPI(
    title="VoiceMesh - Deepgram Voice Agent",
    description="Simple backend to create Deepgram Voice Agent sessions",
    version="2.0.0"
)

# Add CORS middleware to allow browser clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartSessionRequest(BaseModel):
    """Request body for starting a new voice session"""
    metadata: dict | None = None


class StartSessionResponse(BaseModel):
    """Response containing session details"""
    session_id: str
    ws_url: str


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "VoiceMesh",
        "version": "2.0.0",
        "description": "Deepgram Voice Agent Backend",
        "endpoints": {
            "health": "/health",
            "start_session": "/start-session (POST)",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    has_api_key = bool(DEEPGRAM_API_KEY)
    has_agent_id = bool(DEEPGRAM_AGENT_ID)

    return {
        "status": "ok" if (has_api_key and has_agent_id) else "misconfigured",
        "deepgram_api_key_set": has_api_key,
        "deepgram_agent_id_set": has_agent_id,
    }


@app.post("/start-session", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest):
    """
    Creates a Deepgram Voice Agent session and returns the ws_url the client
    should connect to for audio streaming.

    The client (browser, softphone, or app) will:
    1. Call this endpoint to get a session
    2. Connect to the returned ws_url via WebSocket
    3. Stream audio to/from the Deepgram Voice Agent
    """
    if not DEEPGRAM_API_KEY or not DEEPGRAM_AGENT_ID:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: DEEPGRAM_API_KEY or DEEPGRAM_AGENT_ID not set"
        )

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    payload = {"agent_id": DEEPGRAM_AGENT_ID}

    if body.metadata:
        payload["metadata"] = body.metadata

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                DEEPGRAM_VOICE_SESSION_URL,
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
