# RazorFlow Agent — Complete Technical Architecture

This document describes the RazorFlow AI browser agent end-to-end: what it does, how components connect, how browser actions execute, how decisions are made, and how user handoffs and payments are protected. It is written for developers and AI coding agents who need to understand the system without prior context.

---

## Table of contents

1. [What RazorFlow does](#1-what-razorflow-does)
2. [High-level architecture](#2-high-level-architecture)
3. [Execution modes](#3-execution-modes)
4. [System components](#4-system-components)
5. [Repository layout](#5-repository-layout)
6. [End-to-end data flow](#6-end-to-end-data-flow)
7. [Agent workflow (primary: Browser Use executor)](#7-agent-workflow-primary-browser-use-executor)
8. [Agent workflow (legacy: extension DOM executor)](#8-agent-workflow-legacy-extension-dom-executor)
9. [Browser interaction](#9-browser-interaction)
10. [Decision-making process](#10-decision-making-process)
11. [WebSocket protocol](#11-websocket-protocol)
12. [Chrome extension architecture](#12-chrome-extension-architecture)
13. [Overlay UI and visual feedback](#13-overlay-ui-and-visual-feedback)
14. [User handoffs](#14-user-handoffs)
15. [Payment flow (protected)](#15-payment-flow-protected)
16. [Run state and safeguards](#16-run-state-and-safeguards)
17. [Voice and intent routing](#17-voice-and-intent-routing)
18. [Configuration reference](#18-configuration-reference)
19. [Local development](#19-local-development)
20. [Testing](#20-testing)
21. [Design invariants (must not break)](#21-design-invariants-must-not-break)

---

## 1. What RazorFlow does

RazorFlow is an **AI browser agent** built as a Chrome extension plus Python backend. It autonomously navigates e-commerce websites on behalf of a user — searching, comparing products, adding to cart, and proceeding toward checkout — while keeping the user in control of sensitive steps (login, OTP, CAPTCHA, payment confirmation).

**Example user task:**

> "Buy me the cheapest shampoo with good ratings."

**Expected agent behavior:**

1. Extract constraints (category: shampoo, optimize: price + rating).
2. Search with a **short keyword query** (`shampoo`), not the full conversational sentence.
3. Inspect results, compare visible price/rating signals.
4. Open the best-matching product, verify the page.
5. Add to cart / proceed toward checkout.
6. **Pause for user** at login or verification if required.
7. After user resumes, re-read browser state and continue.
8. At checkout, **propose payment** for user confirmation — never pay autonomously.

RazorFlow was built for the **Razorpay AI Buildathon 2026** (Track 01: AI Growth & Agentic Commerce). The demo storefront is `fake-store/` (Next.js on `http://localhost:3000`).

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER                                       │
│         (types/speaks task, confirms payment, completes login)          │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     CHROME EXTENSION (Manifest V3)                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ Popup UI     │  │ Background SW     │  │ Content script + overlay │  │
│  │ (task input) │◄─┤ run-loop, WS    ├─►│ cursor, glow, handoffs   │  │
│  └──────────────┘  │ client, timeline│  └──────────────────────────┘  │
│                    └────────┬────────┘                                  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │ WebSocket ws://127.0.0.1:8765/ws
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AGENT BACKEND (FastAPI, Python)                       │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ bridge_server│  │ RunManager       │  │ BrowserUseRunController  │  │
│  │ (WS router)  │◄─┤ (session state)  ├─►│ (primary executor)       │  │
│  └──────────────┘  └─────────────────┘  └────────────┬─────────────┘  │
│  ┌──────────────┐  ┌─────────────────┐               │                 │
│  │ Policy layer │  │ Groq planner     │ (legacy path) │                 │
│  │ + Razorpay   │  │ + heuristics     │               │                 │
│  │ MCP client   │  └─────────────────┘               │                 │
│  └──────────────┘                                     │                 │
└───────────────────────────────────────────────────────┼─────────────────┘
                                                        │
                                                        ▼
                              ┌─────────────────────────────────────┐
                              │ Browser Use (browser-use library)   │
                              │ Agent + BrowserSession via CDP      │
                              └─────────────────┬───────────────────┘
                                                │
                                                ▼
                              ┌─────────────────────────────────────┐
                              │ Actual browser (Chrome / Chromium)  │
                              │ fake-store, Amazon, etc.            │
                              └─────────────────────────────────────┘
```

**Core principle:** The LLM/agent proposes actions and shopping decisions. **Money never flows through the LLM.** Payment execution goes through a deterministic policy layer and Razorpay MCP only after explicit user confirmation.

---

## 3. Execution modes

The backend supports two browser execution modes, selected by `BROWSER_USE_EXECUTOR_ENABLED` (default: `true`).

| Mode | Env | Who clicks/types | Extension role |
|------|-----|------------------|----------------|
| **`browser_use`** (default) | `BROWSER_USE_EXECUTOR_ENABLED=true` | Browser Use via CDP / launched Chromium | Overlay sync, handoff UI, timeline — **no DOM execution** |
| **`extension_dom`** (legacy) | `BROWSER_USE_EXECUTOR_ENABLED=false` | Extension content script | Full DOM executor + Groq planner loop |

Check active mode at runtime:

```http
GET http://127.0.0.1:8765/health
→ { "executorMode": "browser_use" | "extension_dom", ... }
```

When a run starts in `browser_use` mode, the backend sends `EXECUTOR_MODE` over WebSocket so the extension ignores `NEXT_ACTION` messages.

---

## 4. System components

### 4.1 Chrome extension (`extension/`)

| Part | Path | Responsibility |
|------|------|----------------|
| **Popup** | `popup/` | Task submission, bridge status, run timeline, payment confirm/decline |
| **Background service worker** | `background/` | WebSocket client, run loop, step executor (legacy), voice routing |
| **Content script** | `content/` | Overlay DOM/CSS, cursor/highlight, page context extraction, action playback (legacy) |
| **Shared types/protocol** | `shared/` | `bridge-protocol.ts`, `page-context.ts`, messaging helpers |
| **Offscreen document** | `offscreen/` | Audio capture for voice (Moonshine STT) |

The extension **never** calls Razorpay directly.

### 4.2 Agent backend (`agent-backend/`)

| Part | Path | Responsibility |
|------|------|----------------|
| **Bridge server** | `core/bridge_server.py` | FastAPI app, WebSocket `/ws`, routes messages to executor or legacy planner |
| **Run manager** | `core/run_manager.py` | In-memory run sessions, history, safeguards, handoff/payment state |
| **Browser Use runner** | `core/browser_use_runner.py` | Primary execution: Browser Use Agent + BrowserSession, overlay sync |
| **Browser Use tools** | `core/browser_use_tools.py` | Custom tools: `request_user_handoff`, `propose_checkout_payment` |
| **Browser Use prompt** | `core/browser_use_prompt.py` | Shopping-specific system message extension |
| **Overlay coords** | `core/overlay_coords.py` | Viewport coordinate conversion for cursor/highlight sync |
| **Protocol** | `core/protocol.py` | Pydantic models shared conceptually with extension (camelCase aliases) |
| **Planner (legacy)** | `core/planner.py` | Groq incremental planner when executor is off |
| **Heuristics (legacy)** | `core/heuristics.py` | Deterministic shortcuts before LLM planning |
| **Search query sanitizer** | `core/search_query.py` | Extracts short search keywords from conversational tasks |
| **Browser observer (optional)** | `core/browser_observer.py` | Read-only Browser Use observation for legacy planner |
| **Policy** | `policy/` | Spend limits, validation, audit log, Razorpay MCP client |
| **Voice** | `voice/` | Groq intent classifier API for ambiguous voice transcripts |
| **Config** | `utils/config.py` | Environment loading from repo-root `.env` |

Entry point: `python main.py` → Uvicorn on `127.0.0.1:8765`.

### 4.3 Browser Use ([browser-use](https://github.com/browser-use/browser-use))

Embedded Python library that:

- Controls a real browser via **Chrome DevTools Protocol (CDP)** or launches its own Chromium.
- Runs an **Agent** loop: observe DOM → LLM chooses action → execute → verify → repeat.
- Exposes hooks: `register_new_step_callback`, `register_should_stop_callback`.
- Uses **Groq** (`ChatGroq`) as the LLM provider in RazorFlow.

RazorFlow wraps Browser Use in `BrowserUseRunController` and adds RazorFlow-specific tools and overlay streaming.

### 4.4 Demo storefront (`fake-store/`)

Next.js e-commerce site with search, product pages, cart, login, checkout. Used for development and demos. Product catalog in `fake-store/data/products.ts`.

### 4.5 Policy layer + Razorpay MCP (`agent-backend/policy/`)

| Module | Role |
|--------|------|
| `payment_policy.py` | Deterministic validation (title, amount, currency, spend cap) |
| `payment_executor.py` | Orchestrates policy → audit → MCP call |
| `razorpay_mcp_client.py` | **Single** module that talks to Razorpay MCP (`create_payment_link`) |
| `audit_log.py` | Append-only JSONL audit trail |

**Rule:** The LLM and Browser Use agent **never** call MCP tools directly. They may only call `propose_checkout_payment`, which triggers UI confirmation → policy → MCP.

---

## 5. Repository layout

```
razorflow/
├── extension/                 # Chrome extension (MV3)
│   ├── background/            # Service worker: WS, run loop, voice
│   ├── content/               # Overlay, DOM targeting, action playback (legacy)
│   ├── popup/                 # Extension popup UI
│   ├── shared/                # Protocol, types, page context, timeline
│   └── offscreen/             # Voice audio capture
├── agent-backend/             # Python FastAPI backend
│   ├── core/                  # Bridge, runner, planner, protocol
│   ├── policy/                # Payment policy + MCP + audit
│   ├── voice/                 # Intent classifier
│   └── utils/                 # Config, logging
├── fake-store/                # Demo Next.js store
├── tests/                     # Unit + integration + optional E2E
├── docs/                      # Architecture documentation
└── shared/                    # Cross-project types (if any)
```

See also [AGENTS.md](../AGENTS.md) for contributor rules.

---

## 6. End-to-end data flow

### Primary path (`browser_use` executor)

```
User submits task (popup or overlay dock)
    │
    ▼
Extension background: runLoopController.startRun()
    │  • Sets overlay state: thinking
    │  • Sends START_RUN { task, runId, url?, pageContext? }
    ▼
Backend bridge_server._handle_start_run()
    │  • run_manager.start_run()
    │  • Sends EXECUTOR_MODE { mode: "browser_use" }
    │  • browser_use_controller.start_run()
    ▼
BrowserUseRunController._run_agent_loop()
    │  • Creates BrowserSession (CDP or local Chromium)
    │  • Creates Browser Use Agent (Groq LLM + custom tools)
    │  • agent.run(max_steps=MAX_BROWSER_USE_STEPS)
    │
    ├── Each step: on_step callback
    │       • Updates session.latest_page_context
    │       • Sends AGENT_SYNC { cursor, highlight, actionSummary, url, ... }
    │
    ├── Extension receives AGENT_SYNC
    │       • MOVE_CURSOR, SHOW_HIGHLIGHT, SET_STATE, SET_RUN_PHASE
    │       • Timeline: logAgentSync (deduped)
    │
    ├── Agent calls request_user_handoff → pause_requested
    │       OR propose_checkout_payment → payment_proposal
    │       OR completes task
    │
    └── _finish_run()
            • payment_proposal → PAYMENT_LINK_CONFIRMATION_REQUIRED
            • pause_requested  → RUN_WAITING_FOR_USER
            • else             → RUN_COMPLETE
    ▼
User confirms payment / completes login / resumes
    │
    ▼
Extension sends RESUME_RUN or CONFIRM_PAYMENT_LINK
    │
    ▼
Backend continues Browser Use or executes policy-gated MCP payment
```

### Legacy path (`extension_dom` executor)

```
START_RUN → plan_next_chunk() (Groq + heuristics)
         → NEXT_ACTION { steps[] }
         → extension executes DOM steps (click, type, highlight)
         → ACTION_RESULT { success, pageContext }
         → replan until terminal
```

---

## 7. Agent workflow (primary: Browser Use executor)

### 7.1 Run lifecycle

```
START_RUN
    → EXECUTOR_MODE
    → Browser Use Agent starts
    → [AGENT_SYNC × N steps]
    → Terminal: RUN_COMPLETE | RUN_WAITING_FOR_USER | PAYMENT_LINK_CONFIRMATION_REQUIRED | RUN_ERROR
```

**Cancel:** `CANCEL_RUN` → stops agent task, kills BrowserSession, clears tool state.

**Resume after handoff:** `RESUME_RUN` → reuses `keep_alive` BrowserSession, injects prior `agent.state` for continuity, continues with resume-specific task prompt.

### 7.2 BrowserUseRunController

File: `agent-backend/core/browser_use_runner.py`

Key behaviors:

- **BrowserSession:** `cdp_url` from `BROWSER_USE_CDP_URL` if set; otherwise launches browser (`BROWSER_USE_HEADLESS`, default `false` for visible automation).
- **Initial navigation:** `initial_actions=[{navigate: {url}}]` when `start_url` provided.
- **Step callback:** Converts Browser Use DOM state → `PageContext`, emits `AGENT_SYNC` with viewport-correct cursor/highlight (`overlay_coords.py`).
- **Stop conditions:** `register_should_stop_callback` returns true on cancel or when handoff/payment tool sets `pause_requested` → `InterruptedError` → `_finish_run`.
- **Failure:** Uncaught exceptions → `RUN_ERROR`, session cleanup (fail-closed).

### 7.3 Custom Browser Use tools

File: `agent-backend/core/browser_use_tools.py`

| Tool | Purpose | Side effects |
|------|---------|--------------|
| `request_user_handoff(reason)` | Login, OTP, CAPTCHA, address confirmation | Sets `pause_requested`, stores handoff message |
| `propose_checkout_payment(title, description, amount_paise, currency)` | Checkout total ready | Sets `payment_proposal`, pauses agent |

These tools **do not** execute payment or bypass the user.

### 7.4 Shopping prompt rules

File: `agent-backend/core/browser_use_prompt.py`

Instructs the agent to: use short search queries, compare price/rating, verify cart changes, hand off for credentials, never enter payment credentials, call `propose_checkout_payment` at checkout.

---

## 8. Agent workflow (legacy: extension DOM executor)

When `BROWSER_USE_EXECUTOR_ENABLED=false`:

1. **`plan_next_chunk()`** (`core/planner.py`) runs each turn:
   - Optional heuristic shortcut (`core/heuristics.py`)
   - Optional read-only browser-use observation (`core/browser_observer.py`)
   - Groq LLM call with page context, history, product cards
2. Returns up to **2 steps** per chunk (`MAX_STEPS_PER_CHUNK`).
3. Backend sends **`NEXT_ACTION`** to extension.
4. Extension **`executeActionStep()`** runs DOM actions via content script.
5. Extension sends **`ACTION_RESULT`** with verified `pageContext`.
6. Loop until `terminal`: `continue`, `complete`, `wait_for_user`, `ready_for_payment_link`.

**Search sanitization:** `sanitize_plan_steps()` rewrites overly chatty search text via `core/search_query.py`.

---

## 9. Browser interaction

### 9.1 Browser Use execution (primary)

Browser Use controls the browser through CDP:

- **Click, type, scroll, navigate, form fill** — executed by Browser Use's built-in action registry.
- **State observation** — DOM snapshot, interactive element index map, optional vision (`use_vision="auto"`).
- **Verification** — Agent re-reads page after each action; RazorFlow does not claim success without fresh browser state.

### 9.2 CDP attachment (recommended for overlay sync)

Without CDP, Browser Use may launch a **separate** Chromium window. The extension overlay on the user's tab will **not** align with agent actions.

**Recommended setup:**

```powershell
chrome.exe --remote-debugging-port=9222
```

```env
BROWSER_USE_CDP_URL=http://127.0.0.1:9222
```

Open the target site in that Chrome instance. Extension overlay and Browser Use then target the same visible browser.

### 9.3 Overlay coordinate sync

Browser Use element bounds are in **document coordinates**. The overlay cursor/highlight use **`position: fixed`** (viewport coordinates).

`core/overlay_coords.py` converts bounds using:

1. **`clientRects`** from DOM snapshot (preferred), or
2. **`bounds − scroll`** using `page_info.scroll_x/y`.

### 9.4 Legacy extension DOM execution

When executor mode is off, the content script (`content/action-playback.ts`) performs:

- Element resolution by role + `elementIndex` + optional `matchText` (`dom-targeting.ts`)
- Verified typing (`dom-input.ts`) and clicks with pointer event sequence
- Page signature checks before/after actions (fail-closed on connection loss)
- Cursor/highlight from `getBoundingClientRect()` (already viewport-native)

---

## 10. Decision-making process

### 10.1 Browser Use mode (primary)

| Layer | Decides what |
|-------|--------------|
| **Groq LLM** (inside Browser Use Agent) | Next browser action based on live DOM + task + history |
| **Browser Use action registry** | How to execute click/type/scroll/navigate |
| **RazorFlow custom tools** | When to pause for user or propose payment |
| **RazorFlow prompt extension** | Shopping constraints (short queries, rating/price tradeoffs) |
| **Policy layer** | Whether payment proposal is allowed (amount, title, spend cap) |
| **User** | Login, OTP, payment confirmation |

The agent **replans from fresh browser state** each step — no hardcoded checkout sequences.

### 10.2 Legacy planner mode

| Layer | Decides what |
|-------|--------------|
| **Heuristics** | Fast path for obvious next steps (search, add-to-cart patterns) |
| **Groq planner** | 1–2 JSON action steps from numbered page elements |
| **browser-use observer** | Optional supplemental DOM notes (read-only) |
| **RunManager safeguards** | Abort on too many failures, stale pages, max turns |

### 10.3 Page context

Both modes maintain `PageContext`:

```typescript
{
  title: string;
  url: string;
  elements: PageElementSummary[];   // up to 40 interactive elements
  products: PageProductSummary[];   // up to 8 product-like cards
}
```

In Browser Use mode, context is derived from Browser Use DOM state (`page_context_from_browser.py`). In legacy mode, the content script extracts it from the live DOM (`content/page-context.ts`).

---

## 11. WebSocket protocol

**Endpoint:** `ws://127.0.0.1:8765/ws`

Shared definitions: `agent-backend/core/protocol.py` (Python) and `extension/shared/bridge-protocol.ts` (TypeScript).

### Extension → Backend

| Message | Purpose |
|---------|---------|
| `START_RUN` | Begin task `{ task, runId, url?, pageContext? }` |
| `ACTION_RESULT` | Legacy: report step outcome `{ runId, step, success, error?, pageContext? }` |
| `RESUME_RUN` | Continue after user handoff `{ runId, pageContext? }` |
| `CANCEL_RUN` | Abort run |
| `CONFIRM_PAYMENT_LINK` | User approved payment `{ runId, confirmed: true }` |
| `DECLINE_PAYMENT_LINK` | User declined payment |

### Backend → Extension

| Message | Purpose |
|---------|---------|
| `EXECUTOR_MODE` | `{ mode: "browser_use" \| "extension_dom" }` — tells extension whether to execute DOM |
| `AGENT_SYNC` | Overlay sync: `{ phase, url, step, actionSummary, cursor?, highlight? }` |
| `NEXT_ACTION` | Legacy: `{ steps[], turn }` |
| `RUN_WAITING_FOR_USER` | Handoff pause with message |
| `RUN_COMPLETE` | Task finished |
| `RUN_ERROR` | Unrecoverable failure |
| `PAYMENT_LINK_CONFIRMATION_REQUIRED` | Show payment confirm UI + proposal |
| `PAYMENT_LINK_READY` | MCP succeeded, show link |
| `PAYMENT_LINK_FAILED` | Policy or MCP failure (often recoverable) |

### Action step types (legacy DOM)

```typescript
| { action: "set_state"; state: AgentState }
| { action: "type_in_element"; role; text; elementIndex?; matchText? }
| { action: "click_element"; role; elementIndex?; matchText? }
| { action: "highlight_element"; role; elementIndex?; matchText? }
| { action: "wait_for_user" }
| { action: "ready_for_payment_link"; title; description; amountPaise; currency }
```

---

## 12. Chrome extension architecture

### 12.1 Background service worker

| Module | Role |
|--------|------|
| `ws-client.ts` | WebSocket connection, auto-reconnect, dispatches to run loop |
| `run-loop.ts` | Central state machine: handles backend messages, drives overlay |
| `run-session.ts` | Timeline events for popup (attempt/success/failure, payment audit labels) |
| `step-executor.ts` | Legacy: maps action steps → content commands |
| `voice-controller.ts` | Push-to-talk, transcript → intent → start/resume run |

### 12.2 Content script

Injected on all URLs (`manifest.json`). Responsibilities:

- Inject overlay root (`overlay-dom.ts`, `overlay.css`)
- Handle commands: `SET_STATE`, `MOVE_CURSOR`, `SHOW_HIGHLIGHT`, handoff/payment panels
- Extract `pageContext` on request (legacy planner feedback)
- Execute DOM actions (legacy mode only)

### 12.3 Messaging

- **Background → content:** `chrome.tabs.sendMessage` via `shared/messaging.ts` (with PING/reconnect for reliability)
- **Content → background:** `chrome.runtime.sendMessage` for handoff actions, timeline updates
- **Popup → background:** task submit, cancel, resume, payment confirm

---

## 13. Overlay UI and visual feedback

The overlay (`#razorflow-overlay-root`) is a fixed full-viewport layer with `pointer-events: none` (panels and dock re-enable pointer events where needed).

### Visual elements

| Element | Purpose |
|---------|---------|
| **Viewport frame** | Comet-style animated glow when `data-agent-active="true"` |
| **Agent cursor** | Animated pointer showing where the agent is acting |
| **Highlight rect** | Flash highlight on target element |
| **Command dock** | Brand, status label, text/voice input, send button |
| **Toast** | Planning/error transient messages |
| **Waiting panel** | Handoff UI with Resume / Cancel |
| **Payment panels** | Confirm payment / payment link ready |

### Agent states

`idle | listening | thinking | acting | paused | waiting_for_user`

During Browser Use runs, `AGENT_SYNC` drives `acting`/`thinking` state and updates the dock status label with the current `actionSummary` (e.g. `click element`).

### Run phases

`idle | planning | running | complete | error` — controls glow and status messaging.

---

## 14. User handoffs

Handoffs are **first-class**, not hacks. The run state machine supports:

```
RUNNING → WAITING_FOR_USER → RUNNING (after RESUME_RUN)
```

### 14.1 Browser Use handoffs

When the agent detects login, OTP, CAPTCHA, or similar:

1. Calls tool **`request_user_handoff(reason)`**
2. `pause_requested = true` → agent stops cleanly (`InterruptedError`)
3. Backend sends **`RUN_WAITING_FOR_USER`**
4. Extension shows waiting panel (`ENTER_WAITING_FOR_USER`)
5. User completes manual step in the browser
6. User clicks **Resume** → `RESUME_RUN` with fresh `pageContext`
7. Backend **`resume_run()`** — reuses BrowserSession, injects prior agent memory, continues task

### 14.2 Legacy handoffs

Planner returns `terminal: "wait_for_user"` or step `{ action: "wait_for_user" }`. Same UI flow.

### 14.3 Handoff message heuristics

Backend `_user_handoff_message()` inspects page URL/title for login/OTP keywords to craft user-facing copy.

---

## 15. Payment flow (protected)

```
Agent proposes checkout total
    │
    ▼
propose_checkout_payment tool (Browser Use)
  OR ready_for_payment_link step (legacy planner)
    │
    ▼
PAYMENT_LINK_CONFIRMATION_REQUIRED → extension payment panel
    │
    ├── User declines → RUN_WAITING_FOR_USER
    │
    └── User confirms → CONFIRM_PAYMENT_LINK
            │
            ▼
        payment_executor.execute_payment_link_creation()
            │  1. audit: policy_check_started
            │  2. validate_payment_link_proposal() — deterministic rules
            │  3. audit: policy_approved OR policy_blocked
            │  4. razorpay_mcp_client.create_payment_link() — ONLY here
            │  5. audit: payment_link_success OR payment_link_failure
            ▼
        PAYMENT_LINK_READY or PAYMENT_LINK_FAILED
```

### Policy rules (`payment_policy.py`)

- Title and description required
- `amount_paise > 0` and `≤ MAX_SPEND_PAISE` (default ₹5,000)
- Currency must be 3-letter ISO (default `INR`)
- Reference ID: `rf-{runId8}-{attempt}`

### Audit trail

- File: `agent-backend/logs/payment_audit.jsonl`
- HTTP: `GET /audit/payment?runId=...`
- Extension timeline mirrors key policy/MCP events

**The browser agent never autonomously bypasses payment confirmation.**

---

## 16. Run state and safeguards

### RunSession (`core/run_manager.py`)

Tracks per run:

- `status`: `active | waiting_for_user | complete | error | cancelled`
- `planning_turn`, action `history`
- `latest_page_context`, page fingerprint (stale detection)
- `consecutive_failures`, `stale_page_turns`
- `pending_payment_proposal`, `payment_link_attempts`

### Safeguards (`check_safeguards()`)

Aborts with `RUN_ERROR` when:

- `planning_turn > MAX_PLANNING_TURNS` (legacy)
- `consecutive_failures > MAX_CONSECUTIVE_FAILURES`
- `stale_page_turns > MAX_STALE_PAGE_TURNS` (page not changing)

### Fail-closed principles

- Browser connection lost → pause or error, never invent progress
- Action without verified page context → reported as failure (legacy)
- Browser Use exception → `RUN_ERROR` + session cleanup
- Invalid WebSocket messages → dropped with warning

---

## 17. Voice and intent routing

1. User holds push-to-talk (overlay or popup).
2. Offscreen document captures audio → Moonshine STT (local).
3. Transcript sent to backend `POST /voice/classify-intent` (optional Groq fallback).
4. Intent: `new_task`, `resume`, `cancel`, etc.
5. Routes to `startRun`, `resumeRun`, or `cancelRun`.

Voice is auxiliary; typed task input uses the same run loop.

---

## 18. Configuration reference

Environment variables (repo-root `.env`, see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | — | Required for agent LLM |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model id |
| `BROWSER_USE_EXECUTOR_ENABLED` | `true` | Primary vs legacy executor |
| `BROWSER_USE_CDP_URL` | — | Attach to existing Chrome (`http://127.0.0.1:9222`) |
| `BROWSER_USE_HEADLESS` | `false` | Headless when launching own browser |
| `MAX_BROWSER_USE_STEPS` | `40` | Max agent steps per run |
| `BROWSER_USE_OBSERVER_ENABLED` | `false` | Read-only observer for legacy planner |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | — | Test-mode keys for MCP |
| `RAZORPAY_MCP_ENDPOINT` | `https://mcp.razorpay.com/mcp` | MCP server URL |
| `MAX_SPEND_PAISE` | `500000` | Policy spend cap (₹5,000) |
| `MAX_PLANNING_TURNS` | `16` | Legacy planner turn limit |
| `MAX_CONSECUTIVE_FAILURES` | `3` | Legacy failure cap |

---

## 19. Local development

### Start services

```powershell
# Terminal 1 — fake store
cd fake-store
npm run dev
# → http://localhost:3000

# Terminal 2 — agent backend
cd agent-backend
python main.py
# → http://127.0.0.1:8765/health

# Terminal 3 — build/load extension
cd extension
npm run build
# Load extension/dist in chrome://extensions
```

### Optional: CDP Chrome

```powershell
chrome.exe --remote-debugging-port=9222
# Set BROWSER_USE_CDP_URL=http://127.0.0.1:9222 in .env
```

### Typical dev loop

1. Reload extension after `npm run build`
2. Restart backend after Python changes
3. Open fake-store in CDP-attached Chrome
4. Submit task from popup or overlay dock

---

## 20. Testing

```powershell
# Unit + integration (~2s)
python -m pytest tests/ -q

# Live E2E with Browser Use (~3 min, requires GROQ_API_KEY + running backend + fake-store)
$env:RUN_E2E="1"
$env:BROWSER_USE_HEADLESS="true"
python -m pytest tests/ -q
```

| Test file | Covers |
|-----------|--------|
| `tests/agent/test_search_query.py` | Conversational → keyword extraction |
| `tests/agent/test_overlay_coords.py` | Viewport cursor coordinate conversion |
| `tests/agent/test_bridge_executor.py` | WS routing, executor mode |
| `tests/agent/test_browser_use_tools.py` | Handoff/payment tools |
| `tests/agent/test_e2e_browser_use_smoke.py` | Live search flow |
| `tests/agent/test_e2e_scenarios.py` | Search, checkout, resume scenarios |
| `tests/policy/test_payment_policy.py` | Spend limit, validation |

---

## 21. Design invariants (must not break)

1. **LLM never touches payments directly** — only `propose_checkout_payment` / policy / MCP after user confirm.
2. **Every money-related action is logged** — append-only audit trail.
3. **Pause/resume is first-class** — preserve BrowserSession across handoffs; re-read state on resume.
4. **Cursor overlay logic lives in `extension/content/`** — do not duplicate in popup/background.
5. **All Razorpay MCP calls go through `policy/razorpay_mcp_client.py`** — single module.
6. **Browser Use is the execution layer when executor enabled** — do not leave legacy DOM loop as silent fallback.
7. **Fail-closed on browser disconnect** — never report success without verified state.
8. **Short search queries** — sanitize conversational input before typing into search fields.
9. **Overlay uses viewport coordinates** — always convert Browser Use bounds before `MOVE_CURSOR` / `SHOW_HIGHLIGHT`.

---

## Related documents

- [AGENTS.md](../AGENTS.md) — contributor rules for AI/human coders
- [architecture.md](./architecture.md) — short overview (links here)
- [.env.example](../.env.example) — environment template

---

*Last updated to reflect Browser Use as the primary browser execution layer (`BROWSER_USE_EXECUTOR_ENABLED=true` by default).*
