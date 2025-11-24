# VoiceMesh - Deepgram Voice Agent Backend

Create and manage complete Deepgram Voice Agents with STT, LLM, and TTS in one API call. Deploy to Railway in minutes.

## Features

- **Create Full Voice Agents** - STT (Deepgram) + LLM (Claude) + TTS (Deepgram Aura)
- **Session Management** - Create WebSocket sessions for voice streaming
- **Customizable** - Configure system prompts, greetings, voices, and LLM settings
- **Railway-ready** - One-click deployment
- **CORS enabled** - Ready for browser/web clients

## Architecture

```
VoiceMesh Backend
      ↓
Creates Agent via Deepgram API
  - STT: Deepgram (flux-general-en)
  - LLM: Anthropic Claude (claude-4-5-haiku-latest)
  - TTS: Deepgram Aura (aura-2-andromeda-en)
      ↓
Returns agent_id
      ↓
Create Session → Get ws_url
      ↓
Client connects to WebSocket
```

## Quick Start (Local)

### Prerequisites

1. **Deepgram API Key**
   - Sign up at [https://deepgram.com](https://deepgram.com)
   - Go to [Console](https://console.deepgram.com/)
   - Create an API key

2. **Anthropic API Key**
   - Sign up at [https://console.anthropic.com](https://console.anthropic.com)
   - Create an API key

### Installation

```bash
# Clone the repo
git clone https://github.com/kireland3517/VoiceMesh.git
cd VoiceMesh

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your keys:
# DEEPGRAM_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
```

### Run Locally

```bash
# Start the server
python main.py

# Or with uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API available at `http://localhost:8000`

### Test It

**1. Create an agent:**

```bash
curl -X POST http://localhost:8000/create-agent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "leslie_support_agent",
    "system_prompt": "You are a friendly customer support agent for Senior Life Insurance. Your name is Leslie. Speak in a warm, polite manner and assist callers with their questions.",
    "greeting": "Thank you for calling senior life insurance, my name is Leslie. For quality purposes this call may be recorded, may I get your first name?",
    "voice_model": "aura-2-andromeda-en",
    "llm_model": "claude-4-5-haiku-latest"
  }'
```

Response:
```json
{
  "agent_id": "agent_abc123...",
  "message": "Agent 'leslie_support_agent' created successfully"
}
```

**2. Start a session:**

```bash
curl -X POST http://localhost:8000/start-session \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_abc123...",
    "metadata": {"caller_id": "555-1234"}
  }'
```

Response:
```json
{
  "session_id": "session_xyz...",
  "ws_url": "wss://api.deepgram.com/v1/voice/sessions/session_xyz.../stream?token=..."
}
```

## Deploy to Railway

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Deploy VoiceMesh to Railway"
git push origin main
```

### Step 2: Create Railway Project

1. Go to [Railway](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `VoiceMesh` repository

### Step 3: Configure Environment Variables

In Railway → Your Service → **Variables** tab, add:

- `DEEPGRAM_API_KEY` = your Deepgram API key
- `ANTHROPIC_API_KEY` = your Anthropic API key

### Step 4: Generate Public Domain

1. Go to **Settings** → **Networking**
2. Click **"Generate Domain"**
3. Copy your public URL (e.g., `https://voicemesh-production.up.railway.app`)

### Step 5: Test Deployment

```bash
# Set your Railway URL
export RAILWAY_URL="https://your-app.up.railway.app"

# Health check
curl $RAILWAY_URL/health

# Create an agent
curl -X POST $RAILWAY_URL/create-agent \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "support_agent"}'
```

## API Endpoints

### `GET /`

Root endpoint with API information.

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "deepgram_api_key_set": true,
  "anthropic_api_key_set": true,
  "message": "All keys configured"
}
```

### `POST /create-agent`

Create a complete voice agent with STT, LLM, and TTS.

**Request Body:**
```json
{
  "agent_name": "customer_support_agent",
  "system_prompt": "You are a helpful assistant...",
  "greeting": "Hello! How can I help you?",
  "voice_model": "aura-2-andromeda-en",
  "llm_model": "claude-4-5-haiku-latest",
  "llm_temperature": 0.7,
  "stt_model": "flux-general-en",
  "language": "en"
}
```

**Response:**
```json
{
  "agent_id": "agent_abc123",
  "message": "Agent 'customer_support_agent' created successfully"
}
```

**Available Voices:**
- `aura-2-andromeda-en` - Female, professional (recommended for customer service)
- `aura-2-perseus-en` - Male, professional
- `aura-2-hera-en` - Female, warm
- `aura-2-athena-en` - Female, clear
- [See all voices](https://developers.deepgram.com/docs/tts-models)

**Available Claude Models:**
- `claude-4-5-haiku-latest` - Fast, cost-effective (recommended)
- `claude-4-5-sonnet-latest` - Balanced performance
- `claude-opus-4-latest` - Most capable

### `POST /start-session`

Create a session for an existing agent.

**Request Body:**
```json
{
  "agent_id": "agent_abc123",
  "metadata": {
    "caller_id": "555-1234",
    "campaign": "summer_promo"
  }
}
```

**Response:**
```json
{
  "session_id": "session_xyz",
  "ws_url": "wss://api.deepgram.com/v1/voice/sessions/session_xyz/stream?token=..."
}
```

## Client Integration

### Browser Example (JavaScript)

```javascript
// Step 1: Create an agent (one-time setup)
const agentResponse = await fetch('https://your-app.up.railway.app/create-agent', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    agent_name: 'support_agent',
    greeting: 'Hello! How can I help you today?',
    system_prompt: 'You are a helpful assistant.'
  })
});

const { agent_id } = await agentResponse.json();

// Step 2: Create a session for this agent
const sessionResponse = await fetch('https://your-app.up.railway.app/start-session', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ agent_id })
});

const { ws_url } = await sessionResponse.json();

// Step 3: Connect to WebSocket
const ws = new WebSocket(ws_url);

ws.onopen = () => {
  console.log('Connected to voice agent');
  // Start streaming audio from microphone
};

ws.onmessage = (event) => {
  // Receive TTS audio from agent
  const audioData = event.data;
  // Play audio
};
```

## Use Cases

### Customer Support
```json
{
  "agent_name": "support_agent",
  "system_prompt": "You are a friendly customer support agent. Help customers with billing, technical issues, and account questions.",
  "greeting": "Thank you for calling. How can I help you today?",
  "voice_model": "aura-2-andromeda-en"
}
```

### Appointment Scheduling
```json
{
  "agent_name": "scheduler_agent",
  "system_prompt": "You help customers book appointments. Ask for their preferred date, time, and service needed.",
  "greeting": "Hi! I can help you schedule an appointment. What day works best for you?",
  "voice_model": "aura-2-hera-en"
}
```

### Sales Outreach
```json
{
  "agent_name": "sales_agent",
  "system_prompt": "You are an energetic sales representative. Be enthusiastic but not pushy. Focus on customer needs.",
  "greeting": "Hi there! I'm calling to share an exciting offer that might interest you.",
  "voice_model": "aura-2-perseus-en",
  "llm_temperature": 0.8
}
```

## Configuration Guide

### LLM Temperature
- `0.0-0.3`: Deterministic, consistent responses (good for FAQ bots)
- `0.4-0.7`: Balanced (recommended for most use cases)
- `0.8-1.0`: Creative, varied responses (good for sales, casual conversation)

### STT Models
- `flux-general-en`: Best for conversational voice agents (recommended)
- `nova-2`: General-purpose, high accuracy
- [See all models](https://developers.deepgram.com/docs/models-overview)

### System Prompt Tips
1. **Be specific** about the agent's role and personality
2. **Include constraints** (e.g., "Keep responses under 2 sentences")
3. **Define behavior** for common scenarios
4. **Set tone** (formal, casual, empathetic, etc.)

## Cost Estimate

### Per Minute of Voice Call:
- **Deepgram STT**: ~$0.0043/min
- **Anthropic Claude Haiku**: ~$0.005/min (varies by conversation length)
- **Deepgram TTS**: ~$0.015/min
- **Total**: ~$0.025/min or **$1.50/hour**

### Railway Hosting:
- Free tier available
- Paid plans start at $5/month

## Troubleshooting

### "Server misconfigured" error
Make sure both `DEEPGRAM_API_KEY` and `ANTHROPIC_API_KEY` are set in Railway environment variables.

### "Agent created but no agent_id returned"
Check Deepgram API response format. The API might return `id` instead of `agent_id`.

### Can't connect to WebSocket
Ensure the `ws_url` from `/start-session` is valid and not expired.

### CORS errors
Update `allow_origins` in [main.py:32](main.py#L32) to include your frontend domain.

## Next Steps

- **Add phone integration** - Connect to SignalWire/Twilio/Telnyx
- **Add webhooks** - Receive events from Deepgram (transcripts, call ended)
- **Add logging** - Track sessions, costs, and performance
- **Build web UI** - Browser-based voice client
- **Add authentication** - Protect API with API keys or JWT

## Documentation

- **Deepgram Voice Agents**: [https://developers.deepgram.com/docs/configure-voice-agent](https://developers.deepgram.com/docs/configure-voice-agent)
- **Anthropic Claude API**: [https://docs.anthropic.com/](https://docs.anthropic.com/)
- **Railway Docs**: [https://docs.railway.app](https://docs.railway.app)

## Support

- **Issues**: [https://github.com/kireland3517/VoiceMesh/issues](https://github.com/kireland3517/VoiceMesh/issues)

## License

MIT
