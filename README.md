# RazorFlow

<p align="center">
  <img src="logo.png" alt="RazorFlow logo" width="120" />
</p>

**RazorFlow** is an AI commerce agent for the open web. It navigates real storefronts, pauses for human login and checkout steps, and creates Razorpay test-mode payment links only after deterministic policy validation and your explicit confirmation.

Built for the **Razorpay AI Buildathon 2026** (Track 01 — AI Growth & Agentic Commerce).

## Key features

- **Extension-first execution** — the Chrome extension is the only component that acts on live pages
- **Groq incremental planner** — plans 1–2 steps per turn from page context (+ optional browser-use observation)
- **Human-in-the-loop handoffs** — login, OTP, and checkout pause with Resume / Cancel
- **Voice input** — on-device Moonshine STT with Groq intent fallback (optional)
- **Policy-gated payments** — Razorpay MCP `create_payment_link` only after validation + user confirm
- **Audit visibility** — run timeline in the popup and payment audit API for judges and demos

## Architecture (summary)

```
User → Extension popup/overlay → Background run loop → WebSocket → Agent backend
                                                              ↓
                                                    Groq planner (proposals only)
                                                              ↓
                                         Policy gate → Razorpay MCP (payment links)
```

Full diagrams: [docs/architecture.md](./docs/architecture.md)

## Prerequisites

- Node.js 18+
- Python 3.11+
- Chrome (for the extension)
- Razorpay **test-mode** API keys (for payment-link demo)
- Groq API key (for planning)

## Setup

### 1. Environment

```bash
cp .env.example .env
# Add GROQ_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET (test mode)
```

### 2. Fake store

```bash
cd fake-store
cp .env.example .env.local
# Optional: add NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY
# Optional: run fake-store/supabase/schema.sql in your Supabase project
npm install
npm run dev
# Store: http://127.0.0.1:3000
```

The floating Razorflow agent on the site uses the same backend WebSocket as the extension (`NEXT_PUBLIC_AGENT_WS_URL`, default `ws://127.0.0.1:8765/ws`).

### 3. Agent backend

```bash
cd agent-backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
# http://127.0.0.1:8765
```

### 4. Chrome extension

```bash
cd extension
npm install
npm run build
```

Load **`extension/dist/`** as an unpacked extension in `chrome://extensions`.

## Demo flow (recommended)

1. Start **fake-store**, **agent backend**, and load the **extension**
2. Open the fake store (`http://127.0.0.1:3000`)
3. Use the floating Razorflow agent **or** the Chrome extension popup to start a task (e.g. *find cheapest shampoo*)
4. Watch agent status overlays / the run timeline as Razorflow searches and acts
5. When prompted, complete login/checkout manually → **Resume**
6. At payment, review the **confirmation** panel → **Create payment link**
7. Check **Payment audit** for policy + MCP events → **Open payment link**

## API endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Backend health |
| `WS /ws` | Extension ↔ agent bridge |
| `GET /audit/payment?runId=` | Payment audit entries for a run |
| `POST /voice/classify-intent` | Voice resume vs new-task (Groq fallback) |

## Project layout

| Path | Description |
|------|-------------|
| `extension/` | Chrome MV3 agent UI and executor |
| `agent-backend/` | FastAPI bridge, Groq planner, policy, MCP |
| `agent_runtime/` | **V2 supported runtime** (domain skills) |
| `fake-store/` | Demo e-commerce site |
| `packages/` | Published SDK (`razorflow-protocol` → `browser` → `client`) |
| `docs/` | Architecture and diagrams |

**Runtime:** V2 (`agent_runtime/`) is the supported path. V1 (`core/agent_loop.py`) is legacy — see [docs/RUNTIME.md](./docs/RUNTIME.md).

Contributor rules: [AGENTS.md](./AGENTS.md)

## License

Hackathon / MIT (see component licenses).
