import os
import json
import asyncio
import base64
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
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

# Config storage
CONFIG_DIR = Path("agent_configs")
CONFIG_DIR.mkdir(exist_ok=True)
AGENTS_CONFIG_FILE = CONFIG_DIR / "agents.json"
PHONE_MAPPINGS_FILE = CONFIG_DIR / "phone_mappings.json"

if not DEEPGRAM_API_KEY:
    print("WARNING: DEEPGRAM_API_KEY not set")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not set")

# Initialize Anthropic client
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

app = FastAPI(
    title="VoiceMesh - Deepgram Voice Agent Proxy",
    description="WebSocket proxy for Deepgram Voice Agent with configurable AI personalities",
    version="2.1.0"
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
# Agent Configuration Management
# ============================================================================

class AgentConfig(BaseModel):
    """Configuration for creating a voice agent"""
    agent_name: str = Field(description="Name for logging/identification")
    display_name: str = Field(description="Human-readable name for admin panel")
    system_prompt: str = Field(description="System prompt for the LLM")
    greeting: Optional[str] = Field(default=None, description="Initial greeting when call starts")
    voice_model: str = Field(default="aura-2-andromeda-en", description="Deepgram TTS voice")
    cartesia_voice_id: Optional[str] = Field(default=None, description="Cartesia voice ID (if using Cartesia)")
    llm_model: str = Field(default="claude-4-5-haiku-latest", description="Anthropic Claude model")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    stt_model: str = Field(default="flux-general-en", description="Deepgram STT model")
    language: str = Field(default="en")
    use_cartesia: bool = Field(default=True, description="Use Cartesia for TTS instead of Deepgram")
    active: bool = Field(default=True, description="Whether this agent is active")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AgentConfigManager:
    """Manages agent configurations with file-based persistence"""
    
    def __init__(self):
        self.load_default_configs()
    
    def load_default_configs(self):
        """Load default configurations if file doesn't exist"""
        if not AGENTS_CONFIG_FILE.exists():
            default_configs = {
                "caroline_insurance": AgentConfig(
                    agent_name="caroline_insurance",
                    display_name="Caroline - Senior Life Insurance",
                    system_prompt="You are Caroline, a warm and delightful customer support agent for Senior Life Insurance with authentic Southern charm. You grew up in the South and naturally use Southern expressions throughout your speech. Sprinkle in phrases like 'Well bless your heart', 'honey', 'sweetie', 'darlin'', 'sugar', 'y'all', 'I do declare', 'as happy as a clam', 'might could', and 'fixin' to'. Be genuinely caring and empathetic - treat each caller like family. Keep your responses warm, conversational, and friendly, like you're chatting with a neighbor over sweet tea on the porch. Never sound robotic or scripted.",
                    greeting="Well hey there, honey! Thank you so much for callin' Senior Life Insurance - my name's Caroline and I'm just tickled pink to help you today! Now darlin', this call may be recorded for quality purposes. May I get your first name, sweetie?",
                    voice_model="aura-2-andromeda-en",
                    cartesia_voice_id="694f9389-aac1-45b6-b726-9d9369183238",
                    use_cartesia=True
                ),
                "leslie_support": AgentConfig(
                    agent_name="leslie_support",
                    display_name="Leslie - Professional Support",
                    system_prompt="You are Leslie, a friendly and helpful customer support agent for Senior Life Insurance. Your name is Leslie, and you speak in a warm, polite manner. Assist callers with their life insurance questions or requests, providing clear and empathetic responses.",
                    greeting="Thank you for calling senior life insurance, my name is Leslie. For quality purposes this call may be recorded, may I get your first name?",
                    voice_model="aura-2-andromeda-en",
                    cartesia_voice_id="a0e99841-438c-4a64-b679-ae26e5e21b96",
                    use_cartesia=True
                ),
                "sales_agent": AgentConfig(
                    agent_name="sales_agent",
                    display_name="Mike - Sales Representative",
                    system_prompt="You are Mike, an energetic sales representative. Be enthusiastic but not pushy. Focus on understanding customer needs and presenting solutions that genuinely help them.",
                    greeting="Hi! This is Mike from Senior Life Insurance. I have some exciting opportunities that might interest you today. Do you have a few minutes to chat?",
                    voice_model="aura-2-perseus-en",
                    cartesia_voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",
                    use_cartesia=True
                )
            }
            self.save_configs(default_configs)
    
    def get_all_configs(self) -> Dict[str, AgentConfig]:
        """Get all agent configurations"""
        try:
            with open(AGENTS_CONFIG_FILE, 'r') as f:
                data = json.load(f)
            return {k: AgentConfig(**v) for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.load_default_configs()
            return self.get_all_configs()
    
    def get_config(self, agent_name: str) -> Optional[AgentConfig]:
        """Get specific agent configuration"""
        configs = self.get_all_configs()
        return configs.get(agent_name)
    
    def save_config(self, agent_name: str, config: AgentConfig):
        """Save single agent configuration"""
        configs = self.get_all_configs()
        config.updated_at = datetime.now().isoformat()
        configs[agent_name] = config
        self.save_configs(configs)
    
    def save_configs(self, configs: Dict[str, AgentConfig]):
        """Save all configurations to file"""
        data = {k: v.model_dump() for k, v in configs.items()}
        with open(AGENTS_CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def delete_config(self, agent_name: str) -> bool:
        """Delete an agent configuration"""
        configs = self.get_all_configs()
        if agent_name in configs:
            del configs[agent_name]
            self.save_configs(configs)
            return True
        return False
    
    def get_active_configs(self) -> Dict[str, AgentConfig]:
        """Get only active agent configurations"""
        all_configs = self.get_all_configs()
        return {k: v for k, v in all_configs.items() if v.active}

# Global config manager
config_manager = AgentConfigManager()


# ============================================================================
# Phone Number Mapping Management
# ============================================================================

class PhoneNumberMappingManager:
    """Manages phone number to agent mappings with file-based persistence"""

    def __init__(self):
        self.load_mappings()

    def load_mappings(self) -> Dict[str, str]:
        """Load phone number mappings from file"""
        if not PHONE_MAPPINGS_FILE.exists():
            # Create empty mappings file
            default_mappings = {}
            self.save_mappings(default_mappings)
            return default_mappings

        try:
            with open(PHONE_MAPPINGS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_all_mappings(self) -> Dict[str, str]:
        """Get all phone number mappings"""
        return self.load_mappings()

    def get_agent_for_phone(self, phone_number: str) -> Optional[str]:
        """Get agent name for a specific phone number"""
        mappings = self.load_mappings()
        return mappings.get(phone_number)

    def set_mapping(self, phone_number: str, agent_name: str):
        """Set phone number to agent mapping"""
        mappings = self.load_mappings()
        mappings[phone_number] = agent_name
        self.save_mappings(mappings)

    def delete_mapping(self, phone_number: str) -> bool:
        """Delete a phone number mapping"""
        mappings = self.load_mappings()
        if phone_number in mappings:
            del mappings[phone_number]
            self.save_mappings(mappings)
            return True
        return False

    def save_mappings(self, mappings: Dict[str, str]):
        """Save mappings to file"""
        with open(PHONE_MAPPINGS_FILE, 'w') as f:
            json.dump(mappings, f, indent=2)

# Global phone mapping manager
phone_mapping_manager = PhoneNumberMappingManager()


# ============================================================================
# SignalWire Media Streams Bridge (Updated)
# ============================================================================

class SignalWireMediaBridge:
    """
    Bridge between SignalWire Media Streams and Deepgram STT + Claude + Cartesia TTS.
    Now uses dynamic agent configuration instead of hardcoded values.
    """

    def __init__(self, signalwire_ws: WebSocket, agent_config: AgentConfig):
        self.signalwire_ws = signalwire_ws
        self.agent_config = agent_config
        self.system_prompt = agent_config.system_prompt
        self.greeting = agent_config.greeting

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

        # Background tasks
        self.background_tasks = []

    async def start(self):
        """Start the Media Stream bridge"""
        print(f"🚀 Starting Media Stream bridge with agent: {self.agent_config.display_name}")

        # Create HTTP session for Cartesia
        self.http_session = aiohttp.ClientSession()

        # Connect to Deepgram STT
        await self.setup_deepgram_stt()

        # Start SignalWire keep-alive task
        keepalive_task = asyncio.create_task(self.signalwire_keepalive())
        self.background_tasks.append(keepalive_task)

        # Start listening to SignalWire messages (greeting will be sent after "start" event)
        await self.listen_to_signalwire()

    async def setup_deepgram_stt(self):
        """Connect to Deepgram STT via WebSocket"""
        try:
            # Build STT WebSocket URL with parameters from agent config
            stt_url = (
                "wss://api.deepgram.com/v1/listen"
                f"?model={self.agent_config.stt_model}"
                f"&language={self.agent_config.language}"
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

            # Send initial silent frame to prevent timeout
            silent_frame = bytes(960)  # 480 samples * 2 bytes = 960 bytes (20ms L16 @ 24kHz)
            await self.stt_ws.send(silent_frame)

            # Start task to listen for transcriptions
            asyncio.create_task(self.listen_to_stt())

            # Start keep-alive task
            asyncio.create_task(self.deepgram_keepalive())

        except Exception as e:
            print(f"❌ Failed to connect to Deepgram STT: {e}")
            raise

    async def deepgram_keepalive(self):
        """Send keep-alive messages to Deepgram STT to prevent timeout"""
        try:
            while self.stt_ws:
                await asyncio.sleep(5)  # Every 5 seconds
                if self.stt_ws:
                    await self.stt_ws.send(json.dumps({"type": "KeepAlive"}))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"⚠️  Deepgram keep-alive stopped: {e}")

    async def signalwire_keepalive(self):
        """Send periodic silence to keep SignalWire connection alive during long processing"""
        try:
            while True:
                await asyncio.sleep(2.0)  # Every 2 seconds

                # Only send keepalive if we're not actively speaking
                if not self.speaking and self.stream_sid:
                    # Check if connection is still alive
                    if self.signalwire_ws.client_state != WebSocketState.CONNECTED:
                        break

                    try:
                        # Send single silent frame (L16 @ 24kHz)
                        silence = bytes(960)  # 480 samples * 2 bytes = 960 bytes (20ms L16 @ 24kHz)
                        payload = base64.b64encode(silence).decode('utf-8')

                        await self.signalwire_ws.send_json({
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {"payload": payload}
                        })
                    except Exception:
                        break  # Connection closed
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"⚠️  SignalWire keep-alive stopped: {e}")

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
                        # Send brief silence first to prime the audio stream
                        await self.send_silence(duration_ms=100)
                        # Run greeting in background to not block message processing
                        asyncio.create_task(self.speak(self.greeting))

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

                                    # Send to Claude for response (run in background to not block audio)
                                    asyncio.create_task(self.get_claude_response(utterance))

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

            # Stream response from Claude using agent config
            async with anthropic_client.messages.stream(
                model=self.agent_config.llm_model,
                max_tokens=1024,
                temperature=self.agent_config.llm_temperature,
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

            # Send to TTS (Cartesia or Deepgram based on config)
            await self.speak(assistant_response)

        except Exception as e:
            print(f"❌ Error getting Claude response: {e}")
            self.speaking = False

    async def speak(self, text: str):
        """Send text to TTS and play to caller"""
        if self.agent_config.use_cartesia and self.agent_config.cartesia_voice_id:
            await self.speak_cartesia(text)
        else:
            await self.speak_deepgram(text)

    async def speak_cartesia(self, text: str):
        """Send text to Cartesia TTS via HTTP and play to caller"""
        try:
            # Build Cartesia TTS request
            tts_request = {
                "model_id": "sonic-english",
                "transcript": text,
                "voice": {
                    "mode": "id",
                    "id": self.agent_config.cartesia_voice_id,
                    "emotion": ["positivity:high", "curiosity:high"],
                    "speed": "normal"
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
                    audio_bytes = await response.read()
                    await self.stream_audio_to_signalwire(audio_bytes)
                else:
                    error_text = await response.text()
                    print(f"❌ Cartesia TTS error: {response.status} - {error_text}")

        except Exception as e:
            print(f"❌ Error in Cartesia TTS: {e}")
            self.speaking = False

    async def speak_deepgram(self, text: str):
        """Fallback to Deepgram TTS (not implemented in original, placeholder)"""
        print(f"⚠️  Deepgram TTS not implemented, would speak: {text}")
        self.speaking = False

    async def stream_audio_to_signalwire(self, audio_bytes: bytes):
        """Stream audio bytes to SignalWire in chunks"""
        try:
            # Now we're actually speaking - set flag to stop keep-alive
            self.speaking = True

            # Send audio to SignalWire in chunks (L16 @ 24kHz)
            chunk_size = 960  # 480 samples * 2 bytes = 960 bytes (20ms L16 @ 24kHz)
            for i in range(0, len(audio_bytes), chunk_size):
                if not self.speaking:
                    break

                # Check connection state BEFORE sending
                if self.signalwire_ws.client_state != WebSocketState.CONNECTED:
                    print(f"⚠️  WebSocket disconnected, stopping audio")
                    self.speaking = False
                    break

                try:
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
                except Exception as e:
                    print(f"⚠️  Websocket send error: {e}")
                    self.speaking = False
                    break

            self.speaking = False

        except Exception as e:
            print(f"❌ Error streaming audio: {e}")
            self.speaking = False

    async def send_silence(self, duration_ms: int):
        """Send silent L16 frames to keep SignalWire connection alive"""
        try:
            chunk_size = 960  # 480 samples * 2 bytes = 960 bytes (20ms L16 @ 24kHz)
            num_chunks = duration_ms // 20  # 20ms per chunk

            for _ in range(num_chunks):
                silence = bytes(chunk_size)  # All zeros = silence
                payload = base64.b64encode(silence).decode('utf-8')

                try:
                    await self.signalwire_ws.send_json({
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {"payload": payload}
                    })
                    await asyncio.sleep(0.020)  # 20ms per chunk
                except Exception as e:
                    print(f"⚠️  Could not send silence: {e}")
                    break
        except Exception as e:
            print(f"❌ Error in send_silence: {e}")

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
        """Clean up connections and cancel background tasks"""
        print("🧹 Cleaning up connections...")

        # Cancel all background tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket connections
        if self.stt_ws:
            try:
                await self.stt_ws.close()
            except Exception as e:
                print(f"⚠️  Error closing Deepgram STT: {e}")

        # Close HTTP session
        if self.http_session:
            try:
                await self.http_session.close()
            except Exception as e:
                print(f"⚠️  Error closing HTTP session: {e}")


# ============================================================================
# Helper Functions (Updated)
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
# Admin API Endpoints
# ============================================================================

@app.get("/admin/agents", response_model=Dict[str, AgentConfig])
async def get_all_agents():
    """Get all agent configurations"""
    return config_manager.get_all_configs()

@app.get("/admin/agents/{agent_name}", response_model=AgentConfig)
async def get_agent(agent_name: str):
    """Get specific agent configuration"""
    config = config_manager.get_config(agent_name)
    if not config:
        raise HTTPException(status_code=404, detail="Agent not found")
    return config

@app.post("/admin/agents/{agent_name}", response_model=AgentConfig)
async def create_or_update_agent(agent_name: str, config: AgentConfig):
    """Create or update agent configuration"""
    config.agent_name = agent_name  # Ensure consistency
    config_manager.save_config(agent_name, config)
    print(f"💾 Saved agent config: {config.display_name}")
    return config

@app.delete("/admin/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Delete agent configuration"""
    if config_manager.delete_config(agent_name):
        print(f"🗑️  Deleted agent config: {agent_name}")
        return {"message": "Agent deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Agent not found")

@app.get("/admin/agents/{agent_name}/test")
async def test_agent_greeting(agent_name: str):
    """Test an agent's greeting (for preview)"""
    config = config_manager.get_config(agent_name)
    if not config:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "agent_name": config.agent_name,
        "display_name": config.display_name,
        "greeting": config.greeting,
        "voice_model": config.voice_model,
        "cartesia_voice_id": config.cartesia_voice_id,
        "use_cartesia": config.use_cartesia
    }

@app.get("/admin/active-agent")
async def get_active_agent_for_signalwire():
    """Get the default active agent for SignalWire calls"""
    active_configs = config_manager.get_active_configs()
    
    # Default to caroline_insurance, fallback to first active agent
    default_agent = active_configs.get("caroline_insurance")
    if not default_agent and active_configs:
        default_agent = next(iter(active_configs.values()))
    
    if not default_agent:
        raise HTTPException(status_code=404, detail="No active agents found")
    
    return default_agent


# ============================================================================
# Phone Number Mapping API Endpoints
# ============================================================================

@app.get("/admin/phone-mappings")
async def get_all_phone_mappings():
    """Get all phone number to agent mappings"""
    return phone_mapping_manager.get_all_mappings()

@app.post("/admin/phone-mappings")
async def set_phone_mapping(phone_number: str, agent_name: str):
    """Set or update a phone number to agent mapping"""
    # Verify agent exists
    agent = config_manager.get_config(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    phone_mapping_manager.set_mapping(phone_number, agent_name)
    print(f"📞 Mapped {phone_number} → {agent_name}")
    return {
        "phone_number": phone_number,
        "agent_name": agent_name,
        "message": "Phone mapping created successfully"
    }

@app.delete("/admin/phone-mappings/{phone_number}")
async def delete_phone_mapping(phone_number: str):
    """Delete a phone number mapping"""
    if phone_mapping_manager.delete_mapping(phone_number):
        print(f"🗑️  Deleted phone mapping: {phone_number}")
        return {"message": "Phone mapping deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Phone mapping not found")

@app.get("/admin/phone-mappings/{phone_number}")
async def get_phone_mapping(phone_number: str):
    """Get the agent assigned to a specific phone number"""
    agent_name = phone_mapping_manager.get_agent_for_phone(phone_number)
    if not agent_name:
        raise HTTPException(status_code=404, detail="No mapping found for this phone number")

    agent = config_manager.get_config(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    return {
        "phone_number": phone_number,
        "agent_name": agent_name,
        "agent": agent
    }


# ============================================================================
# Main Endpoints (Updated)
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "VoiceMesh",
        "version": "2.1.0",
        "description": "WebSocket Proxy for Deepgram Voice Agents with Admin Panel",
        "endpoints": {
            "health": "GET /health",
            "voice_agent": "WS /agent (with query params for config)",
            "admin_panel": "GET /admin (Admin interface)",
            "admin_api": "GET /admin/agents (API for configurations)",
            "docs": "GET /docs (Swagger UI)"
        },
        "example": "ws://localhost:8000/agent?agent_name=leslie_support"
    }


@app.get("/admin")
async def admin_panel():
    """Admin panel interface"""
    admin_html_path = Path(__file__).parent / "admin.html"
    
    # If admin.html exists in the same directory, serve it
    if admin_html_path.exists():
        with open(admin_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HTMLResponse(content=content)
    
    # Otherwise return a simple message
    return HTMLResponse(content="""
    <html>
        <body>
            <h1>VoiceMesh Admin Panel</h1>
            <p>Admin panel HTML file not found. Please ensure admin.html is in the same directory as main.py</p>
            <p>You can access the API endpoints directly:</p>
            <ul>
                <li><a href="/admin/agents">GET /admin/agents</a> - List all agents</li>
                <li><a href="/health">GET /health</a> - Health check</li>
                <li><a href="/docs">GET /docs</a> - API documentation</li>
            </ul>
        </body>
    </html>
    """)


@app.get("/health")
async def health():
    """Health check endpoint"""
    has_deepgram = bool(DEEPGRAM_API_KEY)
    has_anthropic = bool(ANTHROPIC_API_KEY)
    has_cartesia = bool(CARTESIA_API_KEY)
    
    active_agents = len(config_manager.get_active_configs())

    return {
        "status": "ok" if (has_deepgram and has_anthropic) else "misconfigured",
        "deepgram_api_key_set": has_deepgram,
        "anthropic_api_key_set": has_anthropic,
        "cartesia_api_key_set": has_cartesia,
        "active_agents": active_agents,
        "websocket_url": DEEPGRAM_AGENT_WS_URL
    }


@app.websocket("/agent")
async def voice_agent_websocket(
    websocket: WebSocket,
    agent_name: str = "leslie_support",
    system_prompt: Optional[str] = None,
    greeting: Optional[str] = None,
    voice_model: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_temperature: Optional[float] = None,
    stt_model: Optional[str] = None,
    language: Optional[str] = None
):
    """
    WebSocket endpoint for voice agent connections.
    
    Now supports both stored agent configs and query parameter overrides.
    """
    await websocket.accept()
    print(f"Client connected: {agent_name}")

    # Try to get stored configuration first
    stored_config = config_manager.get_config(agent_name)
    
    if stored_config:
        # Use stored config as base, allow query param overrides
        config = stored_config.model_copy()
        if system_prompt:
            config.system_prompt = system_prompt
        if greeting:
            config.greeting = greeting
        if voice_model:
            config.voice_model = voice_model
        if llm_model:
            config.llm_model = llm_model
        if llm_temperature:
            config.llm_temperature = llm_temperature
        if stt_model:
            config.stt_model = stt_model
        if language:
            config.language = language
            
        print(f"Using stored config for {agent_name} with overrides")
    else:
        # Fallback to query parameters only (legacy behavior)
        config = AgentConfig(
            agent_name=agent_name,
            display_name=f"Legacy {agent_name}",
            system_prompt=system_prompt or "You are a helpful assistant. Speak naturally and be concise.",
            greeting=greeting,
            voice_model=voice_model or "aura-2-andromeda-en",
            llm_model=llm_model or "claude-4-5-haiku-latest",
            llm_temperature=llm_temperature or 0.7,
            stt_model=stt_model or "flux-general-en",
            language=language or "en",
            use_cartesia=False  # Default to Deepgram for legacy
        )
        print(f"Using legacy query params for {agent_name}")

    # Proxy the connection
    await proxy_to_deepgram(websocket, config)


@app.websocket("/agent/signalwire")
async def signalwire_voice_agent(
    websocket: WebSocket,
    agent_name: Optional[str] = None
):
    """
    SignalWire Media Streams WebSocket endpoint.
    Now supports phone number routing with optional agent_name parameter.
    """
    await websocket.accept()
    print("📞 SignalWire Media Stream connected")

    # Get agent configuration
    if agent_name:
        # Use specified agent from phone mapping
        agent_config = config_manager.get_config(agent_name)
        if not agent_config:
            print(f"⚠️  Requested agent '{agent_name}' not found, using default active agent")
            try:
                agent_config = await get_active_agent_for_signalwire()
            except HTTPException:
                agent_config = None
        else:
            print(f"🎯 Using mapped agent: {agent_config.display_name}")
    else:
        # Use default active agent
        try:
            agent_config = await get_active_agent_for_signalwire()
            print(f"🎭 Using default active agent: {agent_config.display_name}")
        except HTTPException:
            agent_config = None

    # Fallback if no agent found
    if not agent_config:
        print("⚠️  No active agents found, using fallback Caroline config")
        agent_config = AgentConfig(
            agent_name="caroline_fallback",
            display_name="Caroline (Fallback)",
            system_prompt="You are Caroline, a warm customer support agent. Be friendly and helpful.",
            greeting="Hello! Thank you for calling. How can I help you today?",
            voice_model="aura-2-andromeda-en",
            use_cartesia=False
        )

    # Initialize Media Stream bridge with dynamic config
    bridge = SignalWireMediaBridge(
        signalwire_ws=websocket,
        agent_config=agent_config
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
    Now supports multiple agent configurations.
    """
    # Get form data from SignalWire
    form_data = await request.form()
    caller = form_data.get("From", "unknown")
    called = form_data.get("To", "unknown")
    call_sid = form_data.get("CallSid", "unknown")

    print(f"📞 Incoming call: {caller} → {called} (SID: {call_sid})")

    # Check if there's a phone number mapping for the called number
    mapped_agent_name = phone_mapping_manager.get_agent_for_phone(called)
    if mapped_agent_name:
        print(f"🎯 Phone mapping found: {called} → {mapped_agent_name}")
    else:
        print(f"📍 No phone mapping for {called}, using default active agent")

    # Get the base URL of this server
    base_url = str(request.base_url).replace("http://", "wss://").replace("https://", "wss://")
    if base_url.endswith("/"):
        base_url = base_url[:-1]

    # Build WebSocket URL with optional agent parameter
    if mapped_agent_name:
        ws_url = f"{base_url}/agent/signalwire?agent_name={mapped_agent_name}"
    else:
        ws_url = f"{base_url}/agent/signalwire"

    # Return TwiML that connects to our WebSocket
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
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
