# RazorFlow Architecture (Overview)

> **Full documentation:** [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) — complete technical reference for developers and AI agents.

RazorFlow is an AI browser agent for agentic commerce: a Chrome extension provides overlay UX and user handoffs; a Python backend orchestrates runs; **Browser Use** controls the real browser; payments go through a deterministic policy gate and Razorpay MCP.

## Quick reference

| Layer | Responsibility | Never does |
|-------|----------------|------------|
| **Chrome extension** | Overlay, cursor sync, timeline, voice, handoff/payment UI | Call Razorpay; execute DOM when `browser_use` mode |
| **Agent backend** | WebSocket bridge, run state, Browser Use runner, policy + MCP | Let LLM call payments directly |
| **Browser Use** | Navigate, click, type, scroll, observe, replan | Bypass payment confirmation |
| **Policy layer** | Validate proposals, audit trail, MCP execution | Trust LLM output blindly |
| **Razorpay MCP** | `create_payment_link` (test mode) | Run without policy + user approval |

## Primary flow (default)

```
User → Overlay → Extension → Backend → Browser Use Agent → Real Browser
                              ↑ AGENT_SYNC (cursor, highlight, status)
```

Legacy mode (`BROWSER_USE_EXECUTOR_ENABLED=false`): extension executes DOM steps from Groq planner `NEXT_ACTION` chunks.

## Health check

```http
GET http://127.0.0.1:8765/health
```

Returns `executorMode: "browser_use" | "extension_dom"`.

See [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) for protocol messages, payment gating, handoffs, configuration, and testing.
