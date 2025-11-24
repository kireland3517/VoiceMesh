import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import websockets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPGRAM_AGENT_WS_URL = "wss://agent.deepgram.com/agent"

if not DEEPGRAM_API_KEY:
    print("WARNING: DEEPGRAM_API_KEY not set")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not set")

app = FastAPI(
    title="VoiceMesh - Deepgram Voice Agent Proxy",
    description="WebSocket proxy for Deepgram Voice Agent with configurable AI personalities",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class AgentConfig(BaseModel):
    """Configuration for creating a voice agent"""
    agent_name: str = Field(default="support_agent", description="Name for logging/identification")
    system_prompt: str = Field(
        default="You are a helpful assistant. Speak naturally and be concise.",
        description="System prompt for the LLM"
    )
    greeting: Optional[str] = Field(
        default=None,
        description="Initial greeting when call starts (optional)"
    )
    voice_model: str = Field(default="aura-2-andromeda-en", description="Deepgram TTS voice")
    llm_model: str = Field(default="claude-4-5-haiku-latest", description="Anthropic Claude model")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    stt_model: str = Field(default="flux-general-en", description="Deepgram STT model")
    language: str = Field(default="en")


# ============================================================================
# Helper Functions
# ============================================================================

def build_agent_config(config: AgentConfig) -> Dict[str, Any]:
    """Build the Deepgram Voice Agent SettingsConfiguration"""
    agent_config: Dict[str, Any] = {
        "type": "Settings",
        "tags": ["voicemesh", config.agent_name],
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
            "language": config.language,
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": config.stt_model,
                    "smart_format": False
                }
            },
            "think": {
                "provider": {
                    "type": "anthropic",
                    "model": config.llm_model,
                    "temperature": config.llm_temperature
                },
                "endpoint": {
                    "url": "https://api.anthropic.com/v1/complete",
                    "headers": {
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01"
                    }
                },
                "prompt": config.system_prompt
            },
            "speak": {
                "provider": {
                    "type": "deepgram",
                    "model": config.voice_model
                }
            }
        }
    }

    # Add greeting if provided
    if config.greeting:
        agent_config["agent"]["greeting"] = config.greeting

    return agent_config


async def proxy_to_deepgram(client_ws: WebSocket, config: AgentConfig):
    """Proxy WebSocket connection between client and Deepgram"""

    if not DEEPGRAM_API_KEY:
        await client_ws.close(code=1008, reason="Server misconfigured: DEEPGRAM_API_KEY not set")
        return

    if not ANTHROPIC_API_KEY:
        await client_ws.close(code=1008, reason="Server misconfigured: ANTHROPIC_API_KEY not set")
        return

    # Build the agent configuration
    settings_config = build_agent_config(config)

    # Connect to Deepgram with API key in subprotocol
    extra_headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}"
    }

    try:
        async with websockets.connect(
            DEEPGRAM_AGENT_WS_URL,
            extra_headers=extra_headers,
            ping_interval=20,
            ping_timeout=10
        ) as deepgram_ws:

            print(f"Connected to Deepgram for agent: {config.agent_name}")

            # Send SettingsConfiguration to Deepgram
            await deepgram_ws.send(json.dumps(settings_config))
            print(f"Sent SettingsConfiguration for {config.agent_name}")

            # Create tasks for bidirectional proxying
            async def client_to_deepgram():
                """Forward messages from client to Deepgram"""
                try:
                    while True:
                        # Receive from client (can be text or binary)
                        data = await client_ws.receive()

                        if "text" in data:
                            await deepgram_ws.send(data["text"])
                        elif "bytes" in data:
                            await deepgram_ws.send(data["bytes"])

                except WebSocketDisconnect:
                    print(f"Client disconnected: {config.agent_name}")
                except Exception as e:
                    print(f"Error in client_to_deepgram: {e}")

            async def deepgram_to_client():
                """Forward messages from Deepgram to client"""
                try:
                    async for message in deepgram_ws:
                        if isinstance(message, bytes):
                            await client_ws.send_bytes(message)
                        else:
                            await client_ws.send_text(message)

                except websockets.exceptions.ConnectionClosed:
                    print(f"Deepgram connection closed: {config.agent_name}")
                except Exception as e:
                    print(f"Error in deepgram_to_client: {e}")

            # Run both directions concurrently
            await asyncio.gather(
                client_to_deepgram(),
                deepgram_to_client(),
                return_exceptions=True
            )

    except websockets.exceptions.WebSocketException as e:
        print(f"WebSocket error: {e}")
        await client_ws.close(code=1011, reason=f"Deepgram connection failed: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        await client_ws.close(code=1011, reason=f"Server error: {str(e)}")


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "VoiceMesh",
        "version": "2.0.0",
        "description": "WebSocket Proxy for Deepgram Voice Agents",
        "endpoints": {
            "health": "GET /health",
            "voice_agent": "WS /agent (with query params for config)",
            "docs": "GET /docs (Swagger UI)"
        },
        "example": "ws://localhost:8000/agent?agent_name=leslie&greeting=Hello!&system_prompt=You+are+Leslie"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    has_deepgram = bool(DEEPGRAM_API_KEY)
    has_anthropic = bool(ANTHROPIC_API_KEY)

    return {
        "status": "ok" if (has_deepgram and has_anthropic) else "misconfigured",
        "deepgram_api_key_set": has_deepgram,
        "anthropic_api_key_set": has_anthropic,
        "websocket_url": DEEPGRAM_AGENT_WS_URL
    }


@app.websocket("/agent")
async def voice_agent_websocket(
    websocket: WebSocket,
    agent_name: str = "support_agent",
    system_prompt: str = "You are a helpful assistant. Speak naturally and be concise.",
    greeting: Optional[str] = None,
    voice_model: str = "aura-2-andromeda-en",
    llm_model: str = "claude-4-5-haiku-latest",
    llm_temperature: float = 0.7,
    stt_model: str = "flux-general-en",
    language: str = "en"
):
    """
    WebSocket endpoint for voice agent connections.

    Client connects here, and VoiceMesh proxies to Deepgram Voice Agent API
    with the specified configuration.

    Example connection:
    ws://localhost:8000/agent?agent_name=leslie&greeting=Hello!&system_prompt=You are Leslie
    """
    await websocket.accept()
    print(f"Client connected: {agent_name}")

    # Build config from query parameters
    config = AgentConfig(
        agent_name=agent_name,
        system_prompt=system_prompt,
        greeting=greeting,
        voice_model=voice_model,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        stt_model=stt_model,
        language=language
    )

    # Proxy the connection
    await proxy_to_deepgram(websocket, config)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
