# RazorFlow — Complete Guide (Architecture, Status & What’s Built)

> **RazorFlow** is an AI commerce agent for the open web. It navigates real storefronts, executes browser actions in the user’s tab, pauses for human login/checkout steps, and creates Razorpay test-mode payment links only after deterministic policy validation and explicit user confirmation.  
> Built for **Razorpay AI Buildathon 2026** (Track 01 — AI Growth & Agentic Commerce).

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [What has been done (recent work)](#2-what-has-been-done-recent-work)
3. [High-level architecture](#3-high-level-architecture)
4. [Agent execution pipeline](#4-agent-execution-pipeline)
5. [State machine & terminal rules](#5-state-machine--terminal-rules)
6. [Backend modules (`agent-backend/`)](#6-backend-modules-agent-backend)
7. [Fake-store embed (`fake-store/`)](#7-fake-store-embed-fake-store)
8. [Chrome extension (`extension/`)](#8-chrome-extension-extension)
9. [WebSocket protocol](#9-websocket-protocol)
10. [Payments & policy layer](#10-payments--policy-layer)
11. [DOM contract (`data-rf-*`)](#11-dom-contract-data-rf-)
12. [Configuration & URLs](#12-configuration--urls)
13. [Testing status](#13-testing-status)
14. [What is NOT built yet](#14-what-is-not-built-yet)
15. [How to run locally](#15-how-to-run-locally)
16. [Design invariants (do not break)](#16-design-invariants-do-not-break)

---

## 1. Executive summary

RazorFlow has **three main surfaces**:

| Surface | Role |
|--------|------|
| **`fake-store/`** | Demo Next.js e-commerce site with an **embedded floating agent** (`<RazorflowAgent />`) |
| **`agent-backend/`** | FastAPI WebSocket bridge, planner, policy, goal verification, Razorpay MCP |
| **`extension/`** | Chrome MV3 extension (alternative client; same WebSocket protocol) |

**Default execution mode for the demo store:** `extension_dom` — the agent plans on the backend and **executes clicks/navigation in the live browser tab** via `fake-store/lib/agent/action-executor.ts`. The LLM never touches payments directly.

**Core loop:**

```
User task → Task interpretation → Observe page → Plan (store fast-path OR LLM) →
Validate action → Execute in browser → Verify result → Repeat →
DONE only when goal_verifier approves
```

---

## 2. What has been done (recent work)

### Agent reliability (runtime)

| Problem | Fix |
|--------|-----|
| Agent reported **DONE** without real browser progress | `goal_verifier.py` is the **only** authority for completion; LLM `terminal=complete` is stripped |
| Gibberish tasks (e.g. `wdwd`) completed instead of clarifying | `task_interpretation.py` → `RUN_NEEDS_CLARIFICATION` |
| `"buy me butter, chips, cooker"` caused **handoff** | Multi-item `"buy me X, Y, Z"` → `add_to_cart` with **separate searches** per item (not `purchase`) |
| Store fast-path used **one combined search** | `store_planner.py` uses `get_active_product_query()` per item |
| Store DOM guard existed but **was never wired** | `agent_loop.py` now calls `try_store_fast_plan` + `apply_store_dom_guard` before LLM |
| `"add snacks and checkout"` split into 2 products | `search_query.py` strips `and checkout` from product lists |
| Checkout auth redirect treated as handoff | `action_policy.py` treats login gate (`?auth=login&next=/checkout`) as **goal reached** for checkout/purchase |
| WebSocket disconnect cancelled **all** runs | Per-connection `connection_id` scoping in `bridge_server.py` / `run_manager.py` |
| Multi-qty add blocked after first click | `action_policy.py` allows repeat add-to-cart until target count met |

### UI (fake-store agent panel)

| Removed | Reason |
|--------|--------|
| Suggestion pills (“Cheapest shampoo…”, etc.) | Cleaner agentic chat |
| “Page snapshot sent to planner” timeline entries | Noise in chat; snapshots still sent to planner **in background** |

### Tests

- **93** agent unit tests passing (4 skipped)
- **9/9** live E2E tasks passing via `tests/agent/run_live_e2e_tasks.py`, including:
  - `buy me amul butter , chips , cooker`
  - `add snacks under ₹200 and checkout`
  - search, add-to-cart, cart, remove, clarification

---

## 3. High-level architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│  USER                                                                       │
│  Types task in Razorflow panel / extension popup / voice                    │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          ▼                                                   ▼
┌─────────────────────────────┐                 ┌─────────────────────────────┐
│  fake-store (embedded UI)    │                 │  Chrome extension (MV3)      │
│  RazorflowAgent + panel      │                 │  popup + content overlay     │
│  useAgentBridge.ts           │                 │  background run-loop         │
│  action-executor.ts          │                 │  step-executor (DOM)         │
└──────────────┬──────────────┘                 └──────────────┬──────────────┘
               │                                                │
               │         WebSocket  ws://127.0.0.1:8765/ws      │
               └────────────────────┬───────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  agent-backend (FastAPI)                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ bridge_server   │  │ RunManager        │  │ agent_loop               │  │
│  │ (WS router)     │◄─┤ sessions, history │◄─┤ interpret→plan→validate  │  │
│  └─────────────────┘  └──────────────────┘  └───────────┬─────────────┘  │
│  ┌─────────────────┐  ┌──────────────────┐              │                 │
│  │ store_planner   │  │ plan_guard_store │ (0-LLM path) │                 │
│  │ + action_policy │  │ goal_verifier    │              ▼                 │
│  └─────────────────┘  └──────────────────┘  ┌─────────────────────────┐  │
│  ┌─────────────────┐  ┌──────────────────┐  │ planner.py (LLM fallback)│  │
│  │ policy/         │  │ Razorpay MCP     │  └─────────────────────────┘  │
│  │ audit + payment │  │ (payment links)  │                               │
│  └─────────────────┘  └──────────────────┘                               │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ browser_use_runner (optional; BROWSER_USE_EXECUTOR_ENABLED=true)     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  Live browser tab (fake-store) │
                    │  DOM actions + page context    │
                    └───────────────────────────────┘
```

### Execution modes

| Mode | Env | Who acts on the page |
|------|-----|----------------------|
| **`extension_dom`** (default) | `BROWSER_USE_EXECUTOR_ENABLED=false` | fake-store / extension content scripts |
| **`browser_use`** | `BROWSER_USE_EXECUTOR_ENABLED=true` | Browser Use library via CDP; UI shows overlay sync only |

Check: `GET http://127.0.0.1:8765/health` → `executorMode`.

---

## 4. Agent execution pipeline

Every run follows this pipeline (see `agent-backend/core/agent_loop.py`):

```
1. TASK_RECEIVED        START_RUN over WebSocket
2. TASK_INTERPRETATION  task_interpretation.py + task_intent.py
                        → actionable vs needs_clarification
                        → goal: search | add_to_cart | view_cart | checkout | purchase | remove | …
3. OBSERVING            PageContext from client (URL, elements, products, cart lines, optional screenshot)
4. PRE_PLAN_VERIFY      goal_verifier.approve_completion() — early exit if goal already met
5. STORE_FAST_PATH      try_store_fast_plan() + apply_store_dom_guard() — 0 LLM when possible
6. PLANNING             planner.py → OpenRouter / Groq / Gemini (fallback chain)
7. ACTION_VALIDATION    action_policy.py — strip fake complete, inject fallbacks, block bad steps
8. EXECUTING            NEXT_ACTION → client runs action-executor
9. VERIFYING            Client returns ACTION_RESULT { success, verified, pageContext }
10. record_verified_action → milestones, verified_progress_count
11. Loop to step 3 until goal_verifier approves → RUN_COMPLETE
```

**Structured logs** (backend): `[RUN] [INTENT] [OBSERVE] [PLAN] [ACTION] [EXECUTE] [VERIFY] [STATE] [RECOVERY] [DONE]` via `execution_log.py`.

### Planning layers (fast → slow)

| Layer | File | When |
|-------|------|------|
| **Store fast path** | `store_planner.py` | Home → `/search?q=…` on RazorFlow Market |
| **Store DOM guard** | `plan_guard_store.py` | Search, pick product, add to cart, open cart, proceed checkout, multi-item lists |
| **Action policy** | `action_policy.py` | Block LLM complete, login handoff rules, fallbacks |
| **LLM planner** | `planner.py` | When deterministic path has no next step |
| **Planner repair** | `planner_repair.py` | Fix missing `role`, relative URLs before validation |

---

## 5. State machine & terminal rules

### Agent phases (`agent_phase.py`)

`observing` → `planning` → `action_validation` → `executing` → `verifying` → `recovering` → `goal_reached` | `handoff` | `needs_clarification` | `failed`

### Terminal outcomes (client-visible)

| Message | Meaning |
|---------|---------|
| `RUN_COMPLETE` | Goal verified in browser state |
| `RUN_NEEDS_CLARIFICATION` | Task gibberish / not actionable |
| `RUN_WAITING_FOR_USER` | Handoff (login, OTP, or planner stuck) — user taps **Resume** |
| `RUN_ERROR` | Safeguards (max turns, consecutive failures) |
| `PAYMENT_LINK_CONFIRMATION_REQUIRED` | User must confirm payment link creation |

### Critical rule: DONE requires verification

The LLM **cannot** complete a run alone. `goal_verifier.approve_completion()` requires:

- `is_goal_satisfied()` for the parsed goal
- At least one **verified** action (`verified_progress_count >= 1`)
- Required **milestones** (e.g. `verified_search`, `verified_add_to_cart`, `reached_checkout`)

`mark_steps_dispatched()` strips `terminal=complete` from planner output.

### Task intent examples

| User says | Parsed goal | Stop when |
|-----------|-------------|-----------|
| `search for wireless earbuds` | `search` | Search results visible |
| `add good snacks under ₹200` | `add_to_cart` | Item(s) added |
| `buy me butter, chips, cooker` | `add_to_cart` (3 items) | 3 separate adds verified |
| `open my cart` | `view_cart` | On `/cart` |
| `add snacks and checkout` | `checkout` | Checkout page or auth gate |
| `buy good snacks` (single) | `purchase` | Checkout / auth gate |
| `wdwd` | — | `NEEDS_CLARIFICATION` |

---

## 6. Backend modules (`agent-backend/`)

```
agent-backend/
├── main.py                    # Uvicorn entry (port 8765)
├── core/
│   ├── bridge_server.py       # WebSocket /ws, message routing, handoff messages
│   ├── run_manager.py         # RunSession, safeguards, history, connection_id
│   ├── agent_loop.py          # Central interpret → plan → validate loop
│   ├── task_interpretation.py # Actionable vs clarification
│   ├── task_intent.py         # Goal parsing, multi-item lists
│   ├── search_query.py        # Chat → search keywords, product query splitting
│   ├── store_planner.py       # 0-LLM navigate-to-search fast path
│   ├── plan_guard_store.py    # Store-specific DOM planning guards
│   ├── action_policy.py       # Validate/filter planner chunks + fallbacks
│   ├── goal_verifier.py       # Deterministic completion approval
│   ├── planner.py             # LLM planner interface
│   ├── planner_repair.py      # Fix common LLM JSON defects
│   ├── planner_llm.py         # OpenRouter / Groq / Gemini calls
│   ├── protocol.py            # Pydantic wire types (source of truth)
│   ├── execution_log.py         # Structured step logging
│   ├── browser_use_runner.py  # Optional Browser Use executor
│   └── …                      # heuristics, product_compare, observer, etc.
├── policy/
│   ├── payment_policy.py      # Spend limits, proposal validation
│   ├── payment_executor.py    # Razorpay MCP payment link creation
│   └── audit_router.py        # GET /audit/payment
└── voice/
    └── intent_classifier.py   # POST /voice/classify-intent
```

---

## 7. Fake-store embed (`fake-store/`)

### Mounting

```tsx
// app/(store)/layout.tsx
<RazorflowAgent />
```

### Agent library (`lib/agent/`)

| File | Purpose |
|------|---------|
| `useAgentBridge.ts` | WebSocket client, run lifecycle, timeline, handoff/payment state |
| `bridge-protocol.ts` | TypeScript wire types (mirror of `protocol.py`) |
| `action-executor.ts` | click, type, navigate, highlight; verifies cart/URL changes |
| `page-context.ts` | DOM → `PageContext` (elements, products, cart lines) |
| `page-snapshot.ts` | Optional JPEG screenshot for planner (hidden from chat UI) |
| `dom-targeting.ts` | Element ranking (up to 120 elements) |
| `agent-visual.ts` | In-page cursor + highlight pub/sub |
| `navigation.ts` | SPA `router.push` registry for soft navigations |
| `useAgentSessions.ts` | localStorage session history |

### UI (`components/agent/`)

| Component | Purpose |
|-----------|---------|
| `RazorflowAgent.tsx` | FAB + panel shell |
| `AgentPanel.tsx` | Chat timeline, compose, handoff, payment confirm |
| `AgentVisualOverlay.tsx` | Cursor animation on page |
| `AgentNavigationBridge.tsx` | Next.js navigation hook |

### Chat timeline (what users see)

- **Task** — user request
- **Action** — e.g. “Adding to cart…”, “Opening search results…”
- **Done** — run finished
- **Handoff** — login / manual step needed
- **Error** — connection or run failure

(No suggestion pills; no snapshot thumbnails in chat.)

---

## 8. Chrome extension (`extension/`)

Parallel client implementing the same WebSocket protocol:

```
extension/
├── background/     # service-worker, ws-client, run-loop
├── content/        # overlay, cursor, step-executor
├── popup/          # React task UI + timeline
└── shared/         # bridge-protocol types
```

**Note:** Running extension + embedded agent on the same tab can duplicate WebSocket clients. Use one or the other for demos.

---

## 9. WebSocket protocol

**Endpoint:** `ws://127.0.0.1:8765/ws` (override: `NEXT_PUBLIC_AGENT_WS_URL`)

### Client → server

| Type | Purpose |
|------|---------|
| `START_RUN` | `{ runId, task, pageContext? }` |
| `ACTION_RESULT` | `{ runId, step, success, verified?, error?, pageContext }` |
| `RESUME_RUN` | After handoff |
| `CANCEL_RUN` | Abort run |
| `CONFIRM_PAYMENT_LINK` / `DECLINE_PAYMENT_LINK` | Payment flow |

### Server → client

| Type | Purpose |
|------|---------|
| `EXECUTOR_MODE` | `extension_dom` or `browser_use` |
| `NEXT_ACTION` | `{ steps[], actionSummary?, screenshotDataUrl? }` |
| `AGENT_SYNC` | Cursor/highlight (browser_use mode) |
| `RUN_COMPLETE` / `RUN_ERROR` / `RUN_WAITING_FOR_USER` / `RUN_NEEDS_CLARIFICATION` | Terminal / pause states |
| `PAYMENT_LINK_CONFIRMATION_REQUIRED` / `PAYMENT_LINK_READY` / `PAYMENT_LINK_FAILED` | Payment |

### Action step types

`navigate_url` · `click_element` · `type_in_element` · `highlight_element` · `wait_for_user` · `ready_for_payment_link` · `set_state`

### PageContext (summary)

```typescript
{
  title, url,
  elements: [{ index, role, tag, text, placeholder, ariaLabel }],
  products: [{ title, priceText, addToCartElementIndex, … }],
  cartLines: [{ title, quantity, removeElementIndex }],
  screenshotDataUrl?: string  // optional, ≤400k chars
}
```

---

## 10. Payments & policy layer

```
LLM proposes cart/checkout
        ↓
policy/payment_policy.py  (price re-check, spend limits)
        ↓
User confirms in UI
        ↓
policy/payment_executor.py → Razorpay MCP create_payment_link
        ↓
policy/audit_router.py     (append-only audit log)
```

**Rules:**

- LLM **never** calls Razorpay MCP directly
- Test-mode keys only (`.env`, never committed)
- Every MCP call logged to audit trail

**MCP server:** `https://mcp.razorpay.com/mcp` (remote) or local Docker if needed.

---

## 11. DOM contract (`data-rf-*`)

The fake-store exposes hooks for reliable agent targeting:

| Attribute | Used for |
|-----------|----------|
| `data-rf-product-card` | Product listing cards |
| `data-rf-add-to-cart` | Add to cart buttons |
| `data-rf-cart-count` | Header cart badge |
| `data-rf-cart-line` / `data-rf-remove-item` | Cart page |
| `data-rf-auth-required` / `data-rf-checkout-gate` | Login/checkout gates |
| `data-rf-agent-root` | Excluded from targeting (agent UI) |

Checkout without login → middleware redirects to `/?auth=login&next=/checkout` (Supabase auth when configured).

---

## 12. Configuration & URLs

| Service | Default URL |
|---------|-------------|
| Fake store | `http://localhost:3000` or `http://localhost:3001` |
| Agent backend | `http://127.0.0.1:8765` |
| WebSocket | `ws://127.0.0.1:8765/ws` |

### Key env vars

**Root `.env`** (backend):

- `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY` — planner LLM chain
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` — test mode
- `BROWSER_USE_EXECUTOR_ENABLED` — `false` = extension_dom (default)

**`fake-store/.env.local`:**

- `NEXT_PUBLIC_AGENT_WS_URL` — WebSocket URL
- `NEXT_PUBLIC_SUPABASE_*` — optional shopper auth
- `NEXT_PUBLIC_AGENT_SCREENSHOT=false` — disable page snapshots

---

## 13. Testing status

### Unit tests

```bash
python -m pytest tests/agent -q
# 93 passed, 4 skipped (as of last run)
```

Key test files:

- `test_goal_verifier.py` — completion cannot happen without verification
- `test_task_intent.py` — goals, multi-item buy lists, checkout parsing
- `test_action_policy.py` — fallbacks, repeat add-to-cart
- `test_agent_loop.py` — store fast path vs LLM
- `test_store_dom_integration.py` — WebSocket integration (mocked LLM)

### Live E2E

```bash
# Requires store on :3001 and backend on :8765
python tests/agent/run_live_e2e_tasks.py
```

Tasks: wdwd, search, compare, add snacks, add 2 snacks, **buy me multi-item**, open cart, remove item, add + checkout.

---

## 14. What is NOT built yet

| Item | Status |
|------|--------|
| **Publishable npm SDK** (`@razorflow/client`, `@razorflow/protocol`) | Not started — fake-store embed is demo-grade |
| **Protocol type generation** from `protocol.py` | Types duplicated in Python, fake-store TS, extension TS |
| **WebSocket auth** (API key / JWT) | Open bridge, local dev only |
| **Headless API** (`RazorflowProvider`, event callbacks) | UI-only integration today |
| **Production payment** | Test-mode only |

Recommended SDK milestone: extract `bridge-protocol` + `useAgentBridge` → packages, generate TS from Python schema.

---

## 15. How to run locally

### Terminal 1 — Store

```bash
cd fake-store
npm install
npm run dev
```

### Terminal 2 — Backend

```bash
cd agent-backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Terminal 3 — Extension (optional)

```bash
cd extension
npm install
npm run build
# Load extension/dist in chrome://extensions
```

### Verify

- `GET http://127.0.0.1:8765/health` → `status: ok`, `executorMode: extension_dom`
- Open store → click Razorflow bubble → run a task

---

## 16. Design invariants (do not break)

1. **LLM never executes payments** — policy layer + user confirm + MCP only.
2. **DONE requires `goal_verifier` approval** — not LLM `terminal=complete`, not screenshots alone.
3. **Pause/resume is first-class** — `RUN_WAITING_FOR_USER` + `RESUME_RUN` with preserved context.
4. **Every money action is audited** — proposal → policy decision → MCP result.
5. **DOM/state is primary truth** — screenshots supplement `PageContext`, not replace it.
6. **Cursor overlay lives in content/embed** — not duplicated in backend logic.
7. **MCP calls only through** `policy/payment_executor.py` (or `razorpay_mcp_client` equivalent).

---

## Agent Runtime V2 (new — default)

V2 replaces the patch-on-patch V1 planner stack with a **single clean loop**:

```
Task → Observe → LLM Plan (1–3 actions) → Execute → Verify → Memory → Replan
```

- Package: `agent_runtime/` (see [docs/AGENT_RUNTIME_V2.md](./AGENT_RUNTIME_V2.md))
- Canonical protocol: `shared/protocol/v2.schema.json`
- Enable: `AGENT_RUNTIME_V2=true` (default). Set `false` to use legacy V1.
- Health: `GET /health` → `agentRuntimeV2: true`

V1 paths (`store_planner`, `plan_guard_store`, etc.) remain in the repo for comparison but are **not used** when V2 is enabled.


| File | Contents |
|------|----------|
| [docs/AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) | Deep technical reference (extension + browser_use focus) |
| [docs/architecture.md](./architecture.md) | Short overview + diagrams |
| [AGENTS.md](../AGENTS.md) | Contributor rules for AI/human devs |
| [README.md](../README.md) | Quick start |

---

*Last updated: reflects agent runtime fixes, store embed UI cleanup, and E2E validation through multi-item buy + checkout flows.*
