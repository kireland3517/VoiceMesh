# VoiceMesh

**Open-source Voice AI SaaS Platform**

VoiceMesh is a multi-tenant Voice AI platform designed to compete with Retell AI and Vapi, offering 60-75% lower costs through custom infrastructure and the innovative MCP (Model Context Protocol) code execution pattern.

---

## Key Features

- **STS (Speech-to-Speech) Voice AI:** Real-time voice conversations with natural latency
- **Multi-Tenant SaaS:** Enterprise-grade isolation with Firecracker microVMs
- **MCP Code Execution:** 98% token reduction compared to traditional function calling
- **CRM Integrations:** Native support for Salesforce, HubSpot, and custom webhooks
- **Custom Voice Pipelines:** Built on Pipecat framework for maximum flexibility
- **Developer-Friendly:** Python-based, comprehensive API, self-serve dashboard

---

## Technology Stack

### Core Voice Pipeline (External APIs)

| Component | Provider | Cost/Min | Rationale |
|-----------|----------|----------|-----------|
| **STT** | Deepgram Nova-3 | $0.0077 | Best accuracy/cost ratio, 11.8ms latency |
| **TTS** | Cartesia Sonic | $0.005 | Excellent voices, 135ms latency, 3x cheaper than ElevenLabs |
| **LLM** | Claude 3.5 Sonnet | $0.003-0.015 | Superior reasoning and tool use |
| **Telephony** | SignalWire | $0.0085 | Reliable SIP trunking |

### Infrastructure (All on Fly.io)

| Component | Provider | Cost/Mo | Rationale |
|-----------|----------|---------|-----------|
| **Compute** | Fly Machines | $2-32 | Firecracker microVMs, 35+ global regions |
| **Database** | Fly Postgres | $0+ | Unmanaged (free) or Managed ($38+) |
| **Cache** | Upstash Redis (via Fly) | $0-10 | Pay-as-you-go or fixed plans |
| **Storage** | Tigris (via Fly) | Usage-based | S3-compatible object storage |
| **Secrets** | Fly Secrets | Free | Encrypted vault for API keys |
| **Monitoring** | Fly Metrics | Free | Built-in Prometheus + Grafana |
| **Logging** | Fly Logs | Free | Centralized, searchable logs |

### Application Framework

| Component | Provider | Rationale |
|-----------|----------|-----------|
| **Framework** | Pipecat | Open-source Python voice AI framework |
| **API** | FastAPI | High-performance async Python |
| **Code Executor** | Docker | Sandboxed MCP code execution |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    VoiceMesh Platform                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐      ┌──────────────┐            │
│  │   FastAPI    │◄────►│   WebSocket  │            │
│  │   REST API   │      │   Voice Hub  │            │
│  └──────┬───────┘      └──────┬───────┘            │
│         │                     │                     │
│         │    ┌────────────────▼────────────┐       │
│         │    │   Pipecat Voice Pipeline    │       │
│         │    │  ┌────┐  ┌────┐  ┌────┐    │       │
│         │    │  │STT │→ │LLM │→ │TTS │    │       │
│         │    │  └────┘  └────┘  └────┘    │       │
│         │    └────────────────┬────────────┘       │
│         │                     │                     │
│         │         ┌───────────▼───────────┐        │
│         │         │  MCP Code Executor    │        │
│         │         │  (Sandboxed Docker)   │        │
│         │         └───────────┬───────────┘        │
│         │                     │                     │
│         └─────────┬───────────┘                     │
│                   │                                  │
│         ┌─────────▼──────────┐                      │
│         │   Function Registry │                      │
│         │   (Per Customer)    │                      │
│         └─────────┬───────────┘                      │
│                   │                                  │
│         ┌─────────▼──────────┐                      │
│         │   CRM Connectors   │                      │
│         │  (SF, HubSpot, etc)│                      │
│         └────────────────────┘                      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Cost Comparison

### Variable Costs (Per Minute)

| Component | Cost/Min |
|-----------|----------|
| STT (Deepgram) | $0.0077 |
| LLM (Claude) | $0.003-0.015 |
| TTS (Cartesia) | $0.005 |
| Telephony (SignalWire) | $0.0085 |
| **Total Variable** | **$0.024-0.036/min** |

### Fixed Costs (Monthly)

| Component | Cost/Mo |
|-----------|---------|
| Fly Machines (1x shared) | $2 |
| Fly Postgres (unmanaged) | $0 |
| Upstash Redis (pay-as-you-go) | ~$2 |
| Storage (5GB) | $0.75 |
| **Total Fixed** | **~$5/mo** |

### Competitive Comparison

| Provider | Cost per Minute | Annual (100K mins) |
|----------|----------------|-------------------|
| **Retell AI** | $0.13 - $0.31 | $15,600 - $37,200 |
| **Vapi** | $0.13 - $0.30 | $15,600 - $36,000 |
| **VoiceMesh** | $0.032 (cost) | $3,200 |

**Savings:** 75-90% lower cost structure

**Pricing Strategy:** Sell at $0.08-0.12/min for 60-73% margin

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker
- PostgreSQL 15+
- Redis 7+

### Installation

```bash
# Clone repository
git clone https://github.com/kireland3517/VoiceMesh.git
cd VoiceMesh

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# DEEPGRAM_API_KEY=your_key_here
# CARTESIA_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
# SIGNALWIRE_PROJECT_ID=your_project_id
# SIGNALWIRE_TOKEN=your_token
# DATABASE_URL=postgresql://user:pass@localhost:5432/voicemesh
# REDIS_URL=redis://localhost:6379

# Run database migrations (coming soon)
# alembic upgrade head

# Start development server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8080
```

### MCP Connector (Fly.io Ops)

- Endpoint: the MCP server is mounted at `/mcp` on the same FastAPI host (e.g., `https://your-app.fly.dev/mcp`).
- Auth: set `FLY_API_TOKEN` in your environment or Fly secret; optionally set `FLY_APP_NAME` to avoid passing the app name in every call.
- Tools: `get_app_overview`, `list_machines`, and `get_recent_logs` (limit + region filters) all return structured JSON.
- Connector form: Name it something like "VoiceMesh Fly Ops", add a short description ("Inspect Fly.io app status, machines, and logs"), use the `/mcp` URL, and select "None" auth unless you add OAuth later.

### Docker Setup (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

## Project Structure

```
voicemesh/
├── docs/
│   ├── DECISION_FRAMEWORK.md      # CEO decision framework
│   ├── ARCHITECTURE.md            # Technical deep dive
│   ├── API_SPECIFICATION.md       # API documentation
│   └── DEPLOYMENT_GUIDE.md        # Production deployment
│
├── src/
│   ├── platform/
│   │   ├── voice_pipeline.py      # Pipecat STS pipeline
│   │   ├── mcp_executor.py        # MCP code execution engine
│   │   ├── customer_functions.py  # Function registry
│   │   └── crm_connectors.py      # CRM integrations
│   │
│   ├── api/
│   │   ├── main.py                # FastAPI application
│   │   ├── routes/                # API endpoints
│   │   │   ├── voice.py           # Voice WebSocket
│   │   │   ├── customers.py       # Customer management
│   │   │   └── functions.py       # Function registration
│   │   └── models/                # Pydantic models
│   │       ├── customer.py
│   │       └── function.py
│   │
│   └── sandboxes/
│       └── docker_executor.py     # Sandboxed code execution
│
├── tests/
│   ├── test_voice_pipeline.py
│   ├── test_mcp_executor.py
│   └── test_security.py
│
├── infrastructure/
│   ├── fly.toml                   # Fly.io configuration
│   ├── terraform/                 # AWS infrastructure (future)
│   └── k8s/                       # Kubernetes configs (future)
│
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Continuous integration
│       └── deploy.yml             # Deployment pipeline
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## API Example

### Start Voice Call

```python
import asyncio
import websockets
import json

async def start_call():
    uri = "wss://voicemesh.fly.dev/voice/customer_123"

    async with websockets.connect(uri) as websocket:
        # Send configuration
        await websocket.send(json.dumps({
            "type": "start",
            "config": {
                "voice": "professional-female",  # Cartesia voice
                "language": "en-US",
                "functions": ["lookup_zipcode", "check_business_hours"]
            }
        }))

        # Stream audio chunks
        with open("audio.wav", "rb") as f:
            while chunk := f.read(8192):
                await websocket.send(chunk)

        # Receive responses
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "audio":
                # Play audio chunk
                play_audio(data["audio"])
            elif data["type"] == "transcript":
                print(f"AI: {data['text']}")

asyncio.run(start_call())
```

### Register Custom Function

```python
import requests

response = requests.post(
    "https://voicemesh.fly.dev/api/v1/functions",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "name": "lookup_customer",
        "description": "Look up customer information by email or phone",
        "parameters": {
            "email": {"type": "string", "required": False},
            "phone": {"type": "string", "required": False}
        },
        "code": """
def lookup_customer(email=None, phone=None):
    import requests
    # Call your CRM API
    response = requests.get(
        f"https://api.salesforce.com/customer",
        params={"email": email, "phone": phone}
    )
    return response.json()
"""
    }
)
```

---

## MCP Code Execution Example

### Traditional Function Calling (NOT USED)

```python
# Every function definition loaded in context (high tokens)
# Every intermediate result flows through LLM (slow)

# 150,000+ tokens per complex interaction
```

### MCP Code Execution (USED IN VOICEMESH)

```python
# Agent generates code dynamically
code = """
from customer_functions import lookup_customer, update_crm

# Only import what's needed
customer = lookup_customer(email="john@example.com")

if customer and customer['status'] == 'active':
    result = update_crm(
        customer_id=customer['id'],
        field='last_contact',
        value='2025-11-17'
    )

print(f"Updated customer {customer['name']}")
"""

# Execute in sandbox, return only final output
# 2,000 tokens (98% reduction)
```

---

## Deployment

### Fly.io (Recommended for MVP)

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch application
fly launch

# Deploy
fly deploy

# Scale
fly scale count 2
fly scale vm shared-cpu-2x --memory 2048
```

### AWS (For Scale)

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for AWS deployment with Fargate + ECS.

---

## Security

### Sandbox Isolation

- **Firecracker microVMs** for VM-level isolation (Fly.io) or **Docker containers** (AWS)
- **Network isolation** per customer
- **Resource limits:** 2 vCPU, 512MB RAM, 30-second timeout
- **Allowlist imports:** Only approved libraries accessible
- **Code review:** All generated code logged and reviewable

### Data Protection

- **Encryption at rest:** AES-256 for stored data
- **Encryption in transit:** TLS 1.3 for all connections
- **Data retention:** 30-day default, customer configurable
- **GDPR compliance:** Right to export and delete
- **SOC2 Type II:** Planned for Month 12

---

## Roadmap

### Phase 1: Foundation (Months 1-3) ✅ In Progress
- [x] Core voice pipeline with Pipecat
- [x] MCP code execution sandbox
- [ ] Multi-tenant architecture
- [ ] Basic CRM integrations (Salesforce, HubSpot)

### Phase 2: Production (Months 4-6)
- [ ] Customer dashboard (React)
- [ ] Function builder UI
- [ ] Call recording and analytics
- [ ] Beta launch with 20-50 customers

### Phase 3: Scale (Months 7-12)
- [ ] AWS migration (with Activate credits)
- [ ] Advanced analytics
- [ ] Multi-language support
- [ ] Enterprise features (SSO, RBAC)

### Phase 4: Enterprise (Year 2)
- [ ] SOC2 Type II certification
- [ ] HIPAA compliance
- [ ] On-premise deployment option
- [ ] White-label solution

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linter
ruff check .

# Format code
black .

# Type checking
mypy src/
```

---

## Support

- **Documentation:** [docs.voicemesh.com](https://docs.voicemesh.com) (coming soon)
- **Discord Community:** [discord.gg/voicemesh](https://discord.gg/voicemesh) (coming soon)
- **Email:** support@voicemesh.com
- **GitHub Issues:** [github.com/kireland3517/VoiceMesh/issues](https://github.com/kireland3517/VoiceMesh/issues)

---

## License

VoiceMesh is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

Built with:
- [Pipecat](https://github.com/pipecat-ai/pipecat) - Voice AI framework
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Deepgram](https://deepgram.com/) - STT provider
- [Cartesia](https://cartesia.ai/) - TTS provider
- [Anthropic Claude](https://anthropic.com/) - LLM provider
- [Fly.io](https://fly.io/) - Cloud platform

Inspired by the need for affordable, flexible Voice AI infrastructure.

---

**Built by [@kireland3517](https://github.com/kireland3517)**

**Star this repo if you find it useful!** ⭐
