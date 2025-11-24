# VoiceMesh - Deepgram Voice Agent Backend

A minimal FastAPI backend for creating and managing Deepgram Voice Agent sessions. Deploy to Railway in minutes.

## Features

- **FastAPI** - Modern, fast async web framework
- **Deepgram Voice Agent** - Create voice sessions via REST API
- **Railway-ready** - One-click deployment
- **CORS enabled** - Ready for browser/web clients
- **Health checks** - Monitor API status and configuration

## Quick Start (Local)

### Prerequisites

1. **Deepgram Account**
   - Sign up at [https://deepgram.com](https://deepgram.com)
   - Create an API key with `voice-agent:*` permissions
   - Create a Voice Agent and note the `agent_id`

### Installation

```bash
# Clone the repo
git clone https://github.com/kireland3517/VoiceMesh.git
cd VoiceMesh

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your DEEPGRAM_API_KEY and DEEPGRAM_AGENT_ID
```

### Run Locally

```bash
# Start the server
python main.py

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

### Test It

```bash
# Check health
curl http://localhost:8000/health

# Start a voice session
curl -X POST http://localhost:8000/start-session \
  -H "Content-Type: application/json" \
  -d '{"metadata": {"test": true}}'
```

You should receive:

```json
{
  "session_id": "vs_...",
  "ws_url": "wss://api.deepgram.com/v1/voice/sessions/vs_.../stream?token=..."
}
```

## Deploy to Railway

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Initial commit: Deepgram Voice Agent backend"
git push origin main
```

### Step 2: Create Railway Project

1. Go to [Railway](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `VoiceMesh` repository
5. Railway will auto-detect Python and deploy

### Step 3: Configure Environment Variables

In Railway → Your Service → **Variables** tab, add:

- `DEEPGRAM_API_KEY` = your Deepgram API key
- `DEEPGRAM_AGENT_ID` = your Deepgram Voice Agent ID

Railway automatically sets `PORT` - no need to configure it.

### Step 4: Set Start Command (if needed)

Railway should auto-detect, but if not:

**Settings → Start Command:**

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Step 5: Deploy

Railway will automatically deploy. Once complete:

1. Go to **Settings → Generate Domain** to get a public URL
2. Test your deployed API:

```bash
curl https://your-app.up.railway.app/health
```

## API Endpoints

### `GET /`

Root endpoint with API information.

### `GET /health`

Health check endpoint. Returns:

```json
{
  "status": "ok",
  "deepgram_api_key_set": true,
  "deepgram_agent_id_set": true
}
```

### `POST /start-session`

Create a new Deepgram Voice Agent session.

**Request:**

```json
{
  "metadata": {
    "customer_id": "123",
    "source": "web_app"
  }
}
```

**Response:**

```json
{
  "session_id": "vs_abc123...",
  "ws_url": "wss://api.deepgram.com/v1/voice/sessions/vs_abc123.../stream?token=..."
}
```

## Client Integration

After getting the `ws_url` from `/start-session`, your client can:

1. **Open a WebSocket** to the `ws_url`
2. **Stream audio** (PCM, Opus, or other formats)
3. **Receive audio** from the Voice Agent (TTS responses)

### Example JavaScript Client

```javascript
// Step 1: Get session from your backend
const response = await fetch('https://your-app.up.railway.app/start-session', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ metadata: { user: 'john' } })
});

const { ws_url } = await response.json();

// Step 2: Connect to Deepgram WebSocket
const ws = new WebSocket(ws_url);

ws.onopen = () => {
  console.log('Connected to Deepgram Voice Agent');
  // Start streaming audio from microphone
};

ws.onmessage = (event) => {
  // Receive TTS audio from agent
  console.log('Received audio:', event.data);
};
```

## Architecture

```
┌─────────┐      ┌──────────────┐      ┌─────────────┐
│ Client  │─────▶│  VoiceMesh   │─────▶│  Deepgram   │
│(Browser)│      │   (Railway)  │      │Voice Agent  │
└─────────┘      └──────────────┘      └─────────────┘
     │                                         │
     └─────────────WebSocket──────────────────┘
```

1. **Client** calls VoiceMesh `/start-session`
2. **VoiceMesh** creates session via Deepgram API
3. **Client** connects directly to Deepgram WebSocket
4. **Audio streams** between client and Deepgram

## Next Steps

- **Add authentication** - Protect your API with API keys or JWT
- **Add logging** - Track sessions, errors, and usage
- **Add webhooks** - Receive events from Deepgram (call started, ended, transcripts)
- **Phone integration** - Connect to SignalWire/Twilio/Telnyx
- **Web UI** - Build a browser-based client

## Cost Estimate

- **Railway**: Free tier available, paid plans start at $5/month
- **Deepgram Voice Agent**: Pay-as-you-go (check Deepgram pricing)

## Troubleshooting

### "Server misconfigured" error

Make sure you've set `DEEPGRAM_API_KEY` and `DEEPGRAM_AGENT_ID` in Railway environment variables.

### Can't connect to WebSocket

Ensure the `ws_url` from `/start-session` is valid and not expired. Sessions may have a TTL.

### CORS errors

If using a custom frontend domain, update the `allow_origins` list in [main.py:36](main.py#L36).

## Support

- **Deepgram Docs**: [https://developers.deepgram.com](https://developers.deepgram.com)
- **Railway Docs**: [https://docs.railway.app](https://docs.railway.app)
- **Issues**: [https://github.com/kireland3517/VoiceMesh/issues](https://github.com/kireland3517/VoiceMesh/issues)

## License

MIT
