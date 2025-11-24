import os
import json
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import websockets
from dotenv import load_dotenv
import aiohttp

# Anthropic SDK for Claude
from anthropic import AsyncAnthropic

# Load environment variables
load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", DEEPGRAM_API_KEY)  # Use Deepgram key as fallback
DEEPGRAM_AGENT_WS_URL = "wss://agent.deepgram.com/agent"
# Cartesia TTS HTTP API - using raw PCM16 @ 24kHz to match SignalWire
CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VOICE_ID = "694f9389-aac1-45b6-b726-9d9369183238"

if not DEEPGRAM_API_KEY:
    print("WARNING: DEEPGRAM_API_KEY not set")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not set")

# Initialize Anthropic client
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

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
# SignalWire Media Streams Bridge
# ============================================================================

class SignalWireMediaBridge:
    """
    Bridge between SignalWire Media Streams and Deepgram STT + Claude + Cartesia TTS.

    SignalWire Protocol:
    - Receives JSON messages with base64 linear16 audio @ 24kHz
    - Sends JSON messages with base64 linear16 audio @ 24kHz

    Deepgram STT:
    - Receives raw linear16 audio @ 24kHz (no conversion needed!)
    - Returns transcriptions via events

    Claude:
    - Receives transcriptions
    - Returns streaming text responses

    Cartesia TTS:
    - Receives text via HTTP POST
    - Returns raw PCM16 audio @ 24kHz
    - Encoded to base64 and sent to SignalWire
    """

    def __init__(self, signalwire_ws: WebSocket, system_prompt: str, greeting: str):
        self.signalwire_ws = signalwire_ws
        self.system_prompt = system_prompt
        self.greeting = greeting

        # State
        self.stream_sid = None
        self.speaking = False
        self.conversation_history = []

        # Deepgram STT WebSocket
        self.stt_ws = None

        # Aiohttp session for Cartesia HTTP API
        self.http_session = None

        # Transcript accumulation
        self.is_finals = []

    async def start(self):
        """Start the Media Stream bridge"""
        print("🚀 Starting Media Stream bridge...")

        # Create HTTP session for Cartesia
        self.http_session = aiohttp.ClientSession()

        # Connect to Deepgram STT
        await self.setup_deepgram_stt()

        # Start listening to SignalWire messages (greeting will be sent after "start" event)
        await self.listen_to_signalwire()

    async def setup_deepgram_stt(self):
        """Connect to Deepgram STT via WebSocket"""
        try:
            # Build STT WebSocket URL with parameters
            # SignalWire sends L16 @ 24kHz, so configure STT to match
            stt_url = (
                "wss://api.deepgram.com/v1/listen"
                "?model=nova-2-phonecall"
                "&language=en"
                "&smart_format=true"
                "&encoding=linear16"
                "&sample_rate=24000"
                "&channels=1"
                "&interim_results=true"
                "&endpointing=300"
                "&utterance_end_ms=1000"
            )

            extra_headers = {
                "Authorization": f"Token {DEEPGRAM_API_KEY}"
            }

            self.stt_ws = await websockets.connect(stt_url, extra_headers=extra_headers)
            print("✅ Deepgram STT connected")

            # Start task to listen for transcriptions
            asyncio.create_task(self.listen_to_stt())

        except Exception as e:
            print(f"❌ Failed to connect to Deepgram STT: {e}")
            raise


    async def listen_to_signalwire(self):
        """Listen for messages from SignalWire"""
        try:
            while True:
                message = await self.signalwire_ws.receive_text()
                data = json.loads(message)
                event = data.get("event")

                if event == "connected":
                    print(f"📱 SignalWire connected: {data}")

                elif event == "start":
                    print(f"▶️  Call started: {data}")
                    self.stream_sid = data.get("streamSid")

                    # Send greeting now that we have stream_sid
                    if self.greeting:
                        print(f"👋 Sending greeting...")
                        await self.speak(self.greeting)

                elif event == "media":
                    # Decode base64 mulaw audio
                    if not self.stream_sid:
                        self.stream_sid = data.get("streamSid")

                    if data["media"]["track"] == "inbound":
                        payload = data["media"]["payload"]
                        audio_bytes = base64.b64decode(payload)

                        # Send raw mulaw audio to Deepgram STT
                        if self.stt_ws:
                            await self.stt_ws.send(audio_bytes)

                elif event == "mark":
                    print(f"✓ Mark event: {data}")

                elif event == "close":
                    print(f"🔚 Call ended: {data}")
                    break

        except WebSocketDisconnect:
            print("📞 SignalWire disconnected")
        except Exception as e:
            print(f"❌ Error in SignalWire listener: {e}")
        finally:
            await self.cleanup()


    async def listen_to_stt(self):
        """Listen for transcriptions from Deepgram STT"""
        try:
            async for message in self.stt_ws:
                # Parse JSON transcription response
                data = json.loads(message)

                # Check for transcript
                if "channel" in data:
                    channel = data["channel"]
                    if "alternatives" in channel and len(channel["alternatives"]) > 0:
                        transcript = channel["alternatives"][0].get("transcript", "")

                        if transcript:
                            is_final = data.get("is_final", False)
                            speech_final = data.get("speech_final", False)

                            if is_final:
                                self.is_finals.append(transcript)

                                if speech_final:
                                    # Complete utterance
                                    utterance = " ".join(self.is_finals)
                                    self.is_finals = []

                                    print(f"\n👤 User: {utterance}")

                                    # Stop speaking if user interrupts (barge-in)
                                    if self.speaking:
                                        print("🛑 Barge-in detected, clearing audio")
                                        await self.clear_audio()

                                    # Send to Claude for response
                                    await self.get_claude_response(utterance)

                                else:
                                    print(f"📝 [Is Final] {transcript}")
                            else:
                                # Interim result - handle barge-in
                                if self.speaking:
                                    print(f"🛑 User speaking, clearing audio")
                                    await self.clear_audio()

        except Exception as e:
            print(f"❌ Error in STT listener: {e}")

    async def get_claude_response(self, user_message: str):
        """Get streaming response from Claude"""
        try:
            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            print(f"🤖 Claude: ", end="", flush=True)

            # Stream response from Claude
            async with anthropic_client.messages.stream(
                model="claude-3-5-haiku-20241022",
                max_tokens=1024,
                system=self.system_prompt,
                messages=self.conversation_history,
            ) as stream:
                assistant_response = ""

                async for text in stream.text_stream:
                    print(text, end="", flush=True)
                    assistant_response += text

            print()  # New line after response

            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_response
            })

            # Send to Cartesia TTS
            await self.speak(assistant_response)

        except Exception as e:
            print(f"❌ Error getting Claude response: {e}")
            self.speaking = False

    async def speak(self, text: str):
        """Send text to Cartesia TTS via HTTP and play to caller"""
        try:
            self.speaking = True

            # Build Cartesia TTS request
            tts_request = {
                "model_id": "sonic-english",
                "transcript": text,
                "voice": {
                    "mode": "id",
                    "id": CARTESIA_VOICE_ID
                },
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": 24000
                }
            }

            # Make HTTP POST request to Cartesia
            async with self.http_session.post(
                CARTESIA_TTS_URL,
                headers={
                    "X-API-Key": CARTESIA_API_KEY,
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json"
                },
                json=tts_request
            ) as response:
                if response.status == 200:
                    print(f"✅ Cartesia TTS success")

                    # Read audio bytes
                    audio_bytes = await response.read()

                    # Send audio to SignalWire in chunks
                    chunk_size = 160 * 2  # 160 samples * 2 bytes (16-bit PCM)
                    for i in range(0, len(audio_bytes), chunk_size):
                        if not self.speaking:
                            break

                        chunk = audio_bytes[i:i + chunk_size]
                        payload = base64.b64encode(chunk).decode('utf-8')

                        await self.signalwire_ws.send_json({
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {
                                "payload": payload
                            }
                        })

                        # Small delay to pace audio streaming
                        await asyncio.sleep(0.020)  # 20ms per chunk
                else:
                    error_text = await response.text()
                    print(f"❌ Cartesia TTS error: {response.status} - {error_text}")

            self.speaking = False

        except Exception as e:
            print(f"❌ Error in speak: {e}")
            self.speaking = False

    async def clear_audio(self):
        """Clear audio buffer (barge-in)"""
        self.speaking = False

        # Clear SignalWire audio buffer
        if self.stream_sid:
            await self.signalwire_ws.send_json({
                "event": "clear",
                "streamSid": self.stream_sid
            })

    async def cleanup(self):
        """Clean up connections"""
        print("🧹 Cleaning up connections...")

        if self.stt_ws:
            await self.stt_ws.close()

        if self.http_session:
            await self.http_session.close()


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


@app.websocket("/agent/signalwire")
async def signalwire_voice_agent(websocket: WebSocket):
    """
    SignalWire Media Streams WebSocket endpoint.

    Handles incoming calls with SignalWire's JSON protocol:
    - Receives base64 mulaw audio from SignalWire
    - Streams to Deepgram STT for transcription
    - Sends transcripts to Claude for responses
    - Converts Claude responses to speech via Deepgram TTS
    - Sends audio back to SignalWire
    """
    await websocket.accept()
    print("📞 SignalWire Media Stream connected")

    # Initialize Media Stream bridge
    bridge = SignalWireMediaBridge(
        signalwire_ws=websocket,
        system_prompt="You are Caroline, a warm and friendly customer support agent for Senior Life Insurance with a charming Southern personality. Speak naturally with Southern expressions like 'y'all', 'honey', 'sweetie', 'bless your heart', and 'darlin'' when appropriate. Be genuinely helpful and empathetic while maintaining that warm Southern hospitality. Keep responses conversational and friendly.",
        greeting="Well hello there! Thank you for calling Senior Life Insurance, my name is Caroline. For quality purposes, this call may be recorded. May I get your first name, honey?"
    )

    try:
        await bridge.start()
    except Exception as e:
        print(f"❌ Error in Media Stream bridge: {e}")
        await websocket.close()


@app.post("/signalwire/incoming")
async def signalwire_incoming_call(request: Request):
    """
    SignalWire webhook for incoming calls.

    Configure this URL in SignalWire phone number settings:
    https://your-railway-app.up.railway.app/signalwire/incoming

    Returns TwiML that connects the call to VoiceMesh WebSocket.
    """
    # Get form data from SignalWire
    form_data = await request.form()
    caller = form_data.get("From", "unknown")
    called = form_data.get("To", "unknown")
    call_sid = form_data.get("CallSid", "unknown")

    print(f"📞 Incoming call: {caller} → {called} (SID: {call_sid})")

    # Get the base URL of this server
    base_url = str(request.base_url).replace("http://", "wss://").replace("https://", "wss://")
    if base_url.endswith("/"):
        base_url = base_url[:-1]

    # Build WebSocket URL - SignalWire doesn't support query parameters in Stream URL!
    ws_url = f"{base_url}/agent/signalwire"

    # Return TwiML that connects to our WebSocket
    # Note: SignalWire doesn't support query params in Stream URL,
    # so we'll use a dedicated endpoint with Leslie config
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" codec="L16@24000h">
            <Parameter name="caller" value="{caller}" />
            <Parameter name="called" value="{called}" />
            <Parameter name="call_sid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>"""

    print(f"🔗 Connecting call to: {ws_url}")

    return Response(content=twiml, media_type="application/xml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
