# VoiceMesh - Deepgram Voice Agent WebSocket Proxy

WebSocket proxy for Deepgram Voice Agent API. Keeps your API keys secure server-side while enabling voice AI conversations with configurable personalities.

## Features

- **WebSocket Proxy** - Client connects to VoiceMesh, VoiceMesh proxies to Deepgram
- **Secure** - API keys stay server-side
- **Configurable** - Customize agent personality, voice, greeting via query parameters
- **Simple** - No agent IDs, no session management - just connect and talk
- **Railway-ready** - Deploy in minutes

## Architecture

```
Client (Browser/App)
      ↓ WebSocket
VoiceMesh (Railway)
  - Receives connection
  - Builds SettingsConfiguration
  - Connects to Deepgram
  - Proxies audio bidirectionally
      ↓ WebSocket
Deepgram Voice Agent API
  - STT: Deepgram (flux-general-en)
  - LLM: Anthropic Claude (claude-4-5-haiku-latest)
  - TTS: Deepgram Aura (aura-2-andromeda-en)
```

## Quick Start (Local)

### 1. Get API Keys

**Deepgram:** [console.deepgram.com](https://console.deepgram.com)
**Anthropic:** [console.anthropic.com](https://console.anthropic.com)

### 2. Setup

```bash
cd voicemesh

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "DEEPGRAM_API_KEY=your_deepgram_key_here" > .env
echo "ANTHROPIC_API_KEY=your_anthropic_key_here" >> .env
```

### 3. Run

```bash
python main.py
```

Server starts on `http://localhost:8000`

### 4. Test

Open `test_client.html` in your browser to test the WebSocket connection!

Or use the WebSocket URL directly:
```
ws://localhost:8000/agent?agent_name=leslie&greeting=Hello!&system_prompt=You+are+Leslie
```

## Deploy to Railway

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Deploy VoiceMesh"
git push origin main
```

### Step 2: Create Railway Project

1. Go to [Railway](https://railway.app)
2. **New Project** → **Deploy from GitHub repo**
3. Choose `VoiceMesh` repository

### Step 3: Set Environment Variables

Railway Dashboard → Variables:
- `DEEPGRAM_API_KEY` = your key
- `ANTHROPIC_API_KEY` = your key

### Step 4: Get Your URL

Settings → Networking → **Generate Domain**

Copy your URL (e.g., `voicemesh-production.up.railway.app`)

### Step 5: Connect

```javascript
const ws = new WebSocket(
  'wss://voicemesh-production.up.railway.app/agent?' +
  'agent_name=leslie&' +
  'greeting=Thank you for calling!&' +
  'system_prompt=You are Leslie, a friendly support agent.'
);

ws.onopen = () => console.log('Connected!');
ws.onmessage = (event) => {
  // event.data contains audio from Deepgram
  playAudio(event.data);
};

// Send audio to Deepgram
microphone.ondata = (audioChunk) => {
  ws.send(audioChunk);
};
```

## API Reference

### `GET /`

Root endpoint with API info.

### `GET /health`

Health check.

**Response:**
```json
{
  "status": "ok",
  "deepgram_api_key_set": true,
  "anthropic_api_key_set": true,
  "websocket_url": "wss://agent.deepgram.com/agent"
}
```

### `WS /agent`

WebSocket endpoint for voice agent connections.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent_name` | string | "support_agent" | Name for logging/identification |
| `system_prompt` | string | "You are a helpful assistant..." | LLM system prompt |
| `greeting` | string | null | Optional initial greeting |
| `voice_model` | string | "aura-2-andromeda-en" | Deepgram TTS voice |
| `llm_model` | string | "claude-4-5-haiku-latest" | Anthropic Claude model |
| `llm_temperature` | float | 0.7 | LLM temperature (0.0-1.0) |
| `stt_model` | string | "flux-general-en" | Deepgram STT model |
| `language` | string | "en" | Agent language |

**Example:**
```
ws://localhost:8000/agent?agent_name=leslie&greeting=Hello!&system_prompt=You+are+Leslie
```

## Configuration Examples

### Leslie (Customer Support)
```javascript
const wsUrl = 'ws://localhost:8000/agent?' + new URLSearchParams({
  agent_name: 'leslie',
  system_prompt: 'You are Leslie, a friendly customer support agent for Senior Life Insurance. Speak warmly and help with life insurance questions.',
  greeting: 'Thank you for calling senior life insurance, my name is Leslie. For quality purposes this call may be recorded, may I get your first name?',
  voice_model: 'aura-2-andromeda-en',
  llm_temperature: '0.7'
});
```

### Sales Agent
```javascript
const wsUrl = 'ws://localhost:8000/agent?' + new URLSearchParams({
  agent_name: 'sales_agent',
  system_prompt: 'You are an energetic sales representative. Be enthusiastic but not pushy.',
  greeting: 'Hi! I have an exciting offer for you today.',
  voice_model: 'aura-2-perseus-en',
  llm_temperature: '0.8'
});
```

### Appointment Scheduler
```javascript
const wsUrl = 'ws://localhost:8000/agent?' + new URLSearchParams({
  agent_name: 'scheduler',
  system_prompt: 'You help schedule appointments. Ask for preferred date and time.',
  greeting: 'Hi! I can help you book an appointment. What day works for you?',
  voice_model: 'aura-2-hera-en'
});
```

## Voice Models

- `aura-2-andromeda-en` - Female, professional (recommended for customer service)
- `aura-2-perseus-en` - Male, professional
- `aura-2-hera-en` - Female, warm
- `aura-2-athena-en` - Female, clear
- [See all voices](https://developers.deepgram.com/docs/tts-models)

## Claude Models

- `claude-4-5-haiku-latest` - Fast, cost-effective (recommended)
- `claude-4-5-sonnet-latest` - Balanced performance
- `claude-opus-4-latest` - Most capable

## Audio Format

**Input (Client → VoiceMesh → Deepgram):**
- Encoding: 16-bit PCM (linear16)
- Sample rate: 24000 Hz
- Format: Raw binary WebSocket frames

**Output (Deepgram → VoiceMesh → Client):**
- Encoding: 16-bit PCM (linear16)
- Sample rate: 24000 Hz
- Format: Raw binary WebSocket frames

## Cost Estimate

**Per Minute:**
- Deepgram STT: ~$0.0043/min
- Anthropic Claude Haiku: ~$0.005/min
- Deepgram TTS: ~$0.015/min
- **Total: ~$0.025/min or $1.50/hour**

**Railway Hosting:**
- Free tier available
- Paid plans start at $5/month

## Client Example (JavaScript)

```javascript
// Connect
const params = new URLSearchParams({
  agent_name: 'leslie',
  system_prompt: 'You are Leslie, a helpful assistant.',
  greeting: 'Hello! How can I help you?'
});

const ws = new WebSocket(`ws://localhost:8000/agent?${params}`);

ws.onopen = async () => {
  console.log('Connected to VoiceMesh!');

  // Get microphone access
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mediaRecorder = new MediaRecorder(stream);

  // Send audio to VoiceMesh
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      ws.send(event.data);
    }
  };

  mediaRecorder.start(100); // Send chunks every 100ms
};

ws.onmessage = (event) => {
  // Receive audio from VoiceMesh (Deepgram TTS)
  if (event.data instanceof Blob) {
    playAudioBlob(event.data);
  } else {
    console.log('Message:', event.data);
  }
};

function playAudioBlob(blob) {
  const audio = new Audio(URL.createObjectURL(blob));
  audio.play();
}
```

## Troubleshooting

### "Server misconfigured" error
Ensure both `DEEPGRAM_API_KEY` and `ANTHROPIC_API_KEY` are set in Railway environment variables.

### WebSocket connection fails
- Check that Railway domain is correct
- Use `wss://` (not `ws://`) for Railway deployment
- Check Railway logs: `flyctl logs` or view in Railway dashboard

### No audio received
- Ensure you're sending 16-bit PCM audio at 24000 Hz
- Check browser console for errors
- Verify microphone permissions

## Logs

Railway → Your Service → **Deployments** → View logs

Or locally:
```bash
python main.py
# Logs appear in terminal
```

## Next Steps

- **Add phone integration** - Connect via Twilio/SignalWire SIP
- **Add authentication** - Protect WebSocket endpoint
- **Add logging** - Track conversations, costs, performance
- **Build web UI** - Full browser-based voice interface
- **Add webhooks** - Receive events (call started, ended, transcripts)

## Documentation

- **Deepgram Voice Agent API**: [developers.deepgram.com/docs/voice-agent](https://developers.deepgram.com/docs/voice-agent)
- **Anthropic Claude API**: [docs.anthropic.com](https://docs.anthropic.com/)
- **Railway Docs**: [docs.railway.app](https://docs.railway.app)

## Support

**Issues**: [github.com/kireland3517/VoiceMesh/issues](https://github.com/kireland3517/VoiceMesh/issues)

## License

MIT
