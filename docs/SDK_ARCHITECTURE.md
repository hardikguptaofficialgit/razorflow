# RazorFlow SDK Architecture

Phase: General Browser Agent + SDK (post V2 stabilization)

## 1. SDK Architecture

```
             RazorFlow SDK (@razorflow/client)
                  │
          ┌───────┴────────┐
          ↓                ↓
    React UI (fake-store)  Headless / Playwright harness
          │                │
          └───────┬────────┘
                  ↓
            Transport (WebSocketTransport)
                  ↓
         Agent Runtime (agent_runtime/ — Python)
                  │
      ┌───────────┼───────────┐
      ↓           ↓           ↓
   Planner     Executor    Verifier
      │           │           │
      └───────────┼───────────┘
                  ↓
           BrowserEnvironment (@razorflow/browser)
                  │
          ┌───────┴────────┐
          ↓                ↓
   FakeStoreEnvironment   ChromeExtensionEnvironment (planned)
          ↓                ↓
      Embedded DOM      Extension content scripts
```

**Separation of concerns**

| Layer | Responsibility | Must NOT know about |
|-------|----------------|---------------------|
| `@razorflow/client` | Run lifecycle, events, transport | DOM, LLM providers, fake-store routes |
| `@razorflow/protocol` | Wire types, observation schema, trace | Implementation details |
| `@razorflow/browser` | `BrowserEnvironment` contract, generic observation | WebSocket, planning |
| `agent_runtime/` | OBSERVE→PLAN→ACT→VERIFY loop | Transport, specific browser |
| Fake store | Demo UI + `FakeStoreEnvironment` | SDK internals |

## 2. Package Structure

```
packages/
  razorflow-protocol/   # Canonical types, wire messages, trace, action safety
  razorflow-browser/    # BrowserEnvironment interface + generic DOM observation
  razorflow-client/     # RazorFlow class, Transport, AgentRun, events
  razorflow-react/      # (future) optional <RazorFlowAgent /> UI
agent_runtime/          # Python runtime (equivalent to planned razorflow-core)
```

Incremental: `razorflow-core` npm package deferred — Python `agent_runtime/` is the canonical runtime today.

## 3. Public SDK API

```typescript
import { RazorFlow } from "@razorflow/client";
import { fakeStoreEnvironment } from "@/lib/agent/fake-store-environment";

const agent = new RazorFlow({
  endpoint: "ws://127.0.0.1:8765/ws",
  apiKey: "...",           // optional — server validates in production
  environment: fakeStoreEnvironment,
});

agent.on("run_started", ({ runId, task }) => {});
agent.on("observing", ({ runId }) => {});
agent.on("planning", ({ runId }) => {});
agent.on("action_started", ({ runId, summary }) => {});
agent.on("action_completed", ({ runId, success, verified, error }) => {});
agent.on("verification", ({ runId, success, verified }) => {});
agent.on("recovery", ({ runId, message }) => {});
agent.on("handoff", ({ runId, message }) => {});
agent.on("completed", ({ runId, message }) => {});
agent.on("failed", ({ runId, message }) => {});

const run = await agent.run({
  task: "Find wireless earbuds under ₹6000 and add the best one to the cart",
});

run.cancel();
await run.resume();
run.status;   // { runId, task, phase, connected, error, waitingMessage }
run.trace;    // RunTrace with steps, metrics
```

Developers do **not** manually orchestrate observe/plan/click — `RazorFlow` owns the loop.

## 4. BrowserEnvironment Interface

```typescript
interface BrowserEnvironment {
  observe(): Promise<BrowserObservation>;
  observeWire(): Promise<PageContextWire>;
  executeStep(step: ActionStep, onProgress?): Promise<StepResult>;
  waitForStable?(): Promise<PageContextWire>;
  navigate?(url: string): Promise<StepResult>;
}
```

**Implementations**

| Class | Location | Notes |
|-------|----------|-------|
| `FakeStoreEnvironment` | `fake-store/lib/agent/fake-store-environment.ts` | Wraps DOM executor; store hints are optional `EnvironmentHints` |
| `ChromeExtensionEnvironment` | Planned in `extension/` | Same protocol, extension content scripts |

## 5. Protocol Design

- **Canonical schema**: `shared/protocol/v2.schema.json`
- **TypeScript types**: `packages/razorflow-protocol/`
- **Wire transport**: WebSocket messages (`START_RUN`, `NEXT_ACTION`, `ACTION_RESULT`, …)
- **Observation**: `BrowserObservation` — generic DOM + semantic groups; `PageContextWire` for backward-compatible transport
- **Action safety**: `read` / `write` / `high_risk` in `actions.ts`; payment via `ready_for_payment_link` stays policy-gated server-side
- **Security (production-ready design)**:
  - API key / JWT on transport connect (`?apiKey=` today; JWT header planned)
  - LLM keys never in client — server-side `LLMProvider` only
  - Run isolation by `runId`; origin validation at bridge layer

## 6. Files Changed (this phase)

| Path | Change |
|------|--------|
| `packages/razorflow-protocol/src/*` | Generic observation, wire, trace, action safety |
| `packages/razorflow-browser/src/*` | `BrowserEnvironment`, `buildBrowserObservation` |
| `packages/razorflow-client/src/index.ts` | Full `RazorFlow`, `WebSocketTransport`, `AgentRun`, events |
| `fake-store/lib/agent/fake-store-environment.ts` | `FakeStoreEnvironment` |
| `fake-store/lib/agent/agent-sdk.ts` | SDK singleton |
| `fake-store/lib/agent/useAgentBridge.ts` | Refactored to use `@razorflow/client` |
| `fake-store/tsconfig.json` | Path aliases for `@razorflow/*` |
| `tests/agent/run_general_web_tasks.py` | General-web E2E harness |
| `tests/agent/general_web_harness.js` | Site-agnostic page context + step execution |
| `docs/SDK_ARCHITECTURE.md` | This document |

## 7. Legacy Code — Isolated, Not Removed

| Component | Status |
|-----------|--------|
| `store_planner`, `plan_guard_store`, `action_policy` | V1 path only when `AGENT_RUNTIME_V2=false` |
| `browser_use_runner` | Extension/legacy executor mode; not SDK core |
| `fake-store/lib/agent/bridge-protocol.ts` | Wire types duplicated for now; converging on `@razorflow/protocol` |
| `agent-backend/core/planner.py` | Legacy planner — isolated behind V1 flag |

**Do not delete blindly** — V1 flag still enables rollback.

## 8. Fake-Store Integration Status

- Embedded agent uses `RazorFlow` client via `useAgentBridge` → `getRazorFlowClient()`
- `FakeStoreEnvironment` implements `BrowserEnvironment`
- Store-specific DOM (`data-rf-*`) confined to:
  - `page-context.ts` (wire hints for planner)
  - `action-executor.ts` (verification helpers)
  - `fake-store-environment.ts` (`EnvironmentHints` only)
- SDK packages have **no** fake-store imports

## 9. Extension Integration Status

- Extension still uses parallel `extension/shared/bridge-protocol.ts` and local WS client
- **Next step**: Replace extension brain with `@razorflow/client` + `ChromeExtensionEnvironment`
- Architecture target documented; not fully wired in this phase

## 10. Real Browser / General-Web Tests

Run (requires backend on `:8765` + Playwright):

```bash
python tests/agent/run_general_web_tasks.py
```

Sites: `example.com`, `books.toscrape.com`, `wikipedia.org`, `httpbin.org/forms/post`

**Latest results: 3/6 passing** (~125s total, ~20s avg per task)

| Task | Result | Notes |
|------|--------|-------|
| example.com heading | PASS | ~5s |
| books.toscrape travel → book | PASS | 16 steps, reached book detail |
| books.toscrape scroll catalog | FAIL | Immediate RUN_ERROR (steps=0) |
| Wikipedia Python search | FAIL | Search submitted empty query |
| httpbin form fill | PASS | Form submitted to `/post` |
| books.toscrape back nav | FAIL | Reached index but RUN_ERROR terminal |

Fix applied: page context `null` href/value fields broke backend validation on real sites — harness + protocol coercion fixed.

## 11. Latency Measurements

Instrument via:

- Client: `run.trace.metrics.totalDurationMs`
- Server: `agent-backend/logs/agent_runtime_v2.jsonl` (`durationMs`, `llm` fields)

Fake-store checkout baseline ~92s (prior phase). General-web tasks report per-task `duration_ms` in harness output.

**Bottleneck order (typical)**: LLM planning → observation/screenshot → DOM extraction → WebSocket round-trips → execution.

Optimize after measuring — do not remove reasoning steps blindly.

## 12. Remaining Limitations

1. `razorflow-react` not yet published — UI remains in fake-store
2. Extension not on SDK client yet
3. Wire types duplicated (`bridge-protocol.ts` vs `@razorflow/protocol`)
4. `PageContextWire` still allows optional `products`/`cartLines` for planner backward compat
5. General-web evaluators are lenient — tighten as agent improves
6. Production auth (JWT, rate limits) designed but not fully implemented on bridge
7. `razorflow-core` npm package deferred — Python runtime is source of truth

## Success Criterion

A developer installs RazorFlow, provides a natural-language task, and RazorFlow independently performs the browser workflow — without implementing observe/plan/click orchestration.

Fake-store is the demo environment; general-web tests prove site-agnostic behavior.
