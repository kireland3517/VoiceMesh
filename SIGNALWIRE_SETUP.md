# SignalWire Phone Number Setup

Connect your SignalWire phone number to VoiceMesh so that incoming calls are handled by Leslie (your Deepgram Voice Agent).

## Prerequisites

1. **VoiceMesh deployed to Railway** with your API keys set
2. **Railway domain** (e.g., `voicemesh-production.up.railway.app`)
3. **SignalWire account** with a phone number

## Step-by-Step Configuration

### Step 1: Get Your VoiceMesh Webhook URL

Your webhook URL will be:
```
https://your-railway-domain.up.railway.app/signalwire/incoming
```

Example:
```
https://voicemesh-production.up.railway.app/signalwire/incoming
```

### Step 2: Configure SignalWire Phone Number

1. **Log in to SignalWire Dashboard**
   - Go to [https://signalwire.com/signin](https://signalwire.com/signin)

2. **Navigate to Phone Numbers**
   - Click **"Phone Numbers"** in left sidebar
   - Click on your phone number

3. **Configure Voice Webhooks**
   - Scroll to **"Voice & Fax"** section
   - Under **"When a call comes in"**:
     - Set to: **Webhook**
     - Method: **POST**
     - URL: `https://your-railway-domain.up.railway.app/signalwire/incoming`

4. **Save Configuration**
   - Click **Save** at the bottom

### Step 3: Test It!

Call your SignalWire phone number. You should hear:

> "Thank you for calling senior life insurance, my name is Leslie. For quality purposes this call may be recorded, may I get your first name?"

Then you can talk to Leslie!

## How It Works

```
Caller
  ↓ Dials your SignalWire number
SignalWire
  ↓ POST /signalwire/incoming
VoiceMesh (Railway)
  ↓ Returns TwiML with WebSocket URL
SignalWire
  ↓ Opens WebSocket to VoiceMesh
  ↓ Streams audio bidirectionally
VoiceMesh
  ↓ Proxies to Deepgram Voice Agent
Deepgram
  ↓ STT → Claude → TTS
  ↓ Audio responses back to caller
```

## Customizing the Agent

The webhook endpoint is currently hard-coded with Leslie's configuration. To customize, edit [main.py:300-306](main.py#L300):

```python
# Build WebSocket URL with custom configuration
ws_url = (
    f"{base_url}/agent?"
    f"agent_name=your_agent_name&"
    f"system_prompt=Your+custom+prompt+here&"
    f"greeting=Your+custom+greeting&"
    f"voice_model=aura-2-andromeda-en"
)
```

## Troubleshooting

### No answer when calling

**Check Railway logs:**
```bash
# In Railway dashboard: Deployments → View Logs
```

Look for:
```
📞 Incoming call: +1234567890 → +10987654321
🔗 Connecting call to: wss://...
```

If you don't see these logs, SignalWire isn't reaching your webhook.

**Verify:**
- Railway domain is correct
- Webhook URL uses `https://` (not `http://`)
- SignalWire webhook is saved properly

### Call connects but no voice

**Check that:**
- `DEEPGRAM_API_KEY` is set in Railway
- `ANTHROPIC_API_KEY` is set in Railway
- Railway health check returns `"status": "ok"`

**Test health endpoint:**
```bash
curl https://your-railway-domain.up.railway.app/health
```

Should return:
```json
{
  "status": "ok",
  "deepgram_api_key_set": true,
  "anthropic_api_key_set": true
}
```

### "Server misconfigured" error

Your API keys aren't set in Railway. Add them:

1. Railway Dashboard → Your Service → **Variables**
2. Add `DEEPGRAM_API_KEY`
3. Add `ANTHROPIC_API_KEY`
4. Railway will auto-redeploy

### Call drops immediately

SignalWire Media Streams requires a secure WebSocket (`wss://`). Ensure your Railway domain uses HTTPS (Railway provides this automatically).

## Audio Format

SignalWire streams audio as:
- **Encoding:** µ-law (8-bit)
- **Sample rate:** 8000 Hz
- **Codec:** PCMU

VoiceMesh converts this to Deepgram's format:
- **Encoding:** linear16 (16-bit PCM)
- **Sample rate:** 24000 Hz

## Cost

**Per Call Minute:**
- SignalWire: ~$0.0085/min (inbound)
- Deepgram + Claude + VoiceMesh: ~$0.025/min
- **Total: ~$0.034/min**

**For a 5-minute call:** $0.17

## Advanced: Multiple Agent Configurations

To support multiple agents, you can create different webhook endpoints:

```python
@app.post("/signalwire/support")
async def support_line(request: Request):
    # Leslie for support
    ...

@app.post("/signalwire/sales")
async def sales_line(request: Request):
    # Different agent for sales
    ...
```

Then configure different SignalWire numbers to use different webhooks.

## Next Steps

- **Add call logging** - Track caller ID, duration, transcripts
- **Add call routing** - Route to different agents based on caller input
- **Add voicemail** - Handle missed calls
- **Add SMS integration** - Send follow-up SMS after calls

## Support

**VoiceMesh Issues:** [github.com/kireland3517/VoiceMesh/issues](https://github.com/kireland3517/VoiceMesh/issues)

**SignalWire Docs:** [signalwire.com/resources/guides](https://signalwire.com/resources/guides)
