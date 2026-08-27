# Agent Runtime V2 — Architecture & Migration

## Why V2 exists

The V1 stack accumulated overlapping planners (`store_planner`, `plan_guard_store`, `heuristics`, `action_policy`, `planner_repair`) that short-circuit the LLM on the fake store. That produced patch-on-patch behavior: repeated clicks, wrong targets, fake completion, and fragile recovery.

**V2 principle:** one runtime loop, one state owner, LLM plans *what* happens next, the browser executor handles *how*.

## V1 architecture map (deprecated path)

```
bridge_server._dispatch_next_chunk
  → plan_next_chunk → agent_loop.plan_next_action
      1. task_interpretation
      2. goal_verifier (early complete)
      3. store_planner (0-LLM navigate)      ← store-specific
      4. plan_guard_store (~565 lines)      ← second planner
      5. action_policy
      OR LLM → plan_guard_store → action_policy again
  → NEXT_ACTION → client action-executor
  → ACTION_RESULT → goal_verifier → replan
```

**State fragmentation:** `RunSession`, `BrowserUseToolState`, client UI state, extension `RunLoopController`.

**Protocol triplication:** `protocol.py`, `fake-store/bridge-protocol.ts`, `extension/shared/bridge-protocol.ts`.

## V2 architecture

```
USER TASK
    ↓
TaskParser (goal + constraints)
    ↓
AgentRuntime (single loop + RunState)
    ↓
BrowserObservation (from PageContext — site-agnostic)
    ↓
LLMPlanner (1–3 actions, short horizon)
    ↓
ActionTranslator → legacy ActionStep (bridge compat)
    ↓
Client BrowserEnvironment (observe / click / type / scroll / navigate)
    ↓
ActionVerifier + GoalVerifier (deterministic)
    ↓
TaskMemory update + RecoveryDetector
    ↓
REPLAN or DONE or HANDOFF
```

### Package layout (`agent_runtime/`)

| Module | Responsibility |
|--------|----------------|
| `state/run_state.py` | **Single source of truth** for a run |
| `task/parser.py` | Natural language → structured goal |
| `observation/browser_state.py` | Rich, compact page representation for LLM |
| `planner/llm_provider.py` | Groq → OpenRouter → Gemini, key rotation |
| `planner/planner.py` | Short-horizon structured planning |
| `executor/actions.py` | Strict V2 action schema |
| `executor/translate.py` | V2 actions → wire `ActionStep` |
| `verifier/goal.py` | Deterministic goal satisfaction |
| `verifier/action_result.py` | Post-action verification |
| `recovery/stuck.py` | Loop / repeat / no-progress detection |
| `memory/task_memory.py` | Facts, failures, remaining work |
| `events/trace.py` | Structured run trace |
| `bridge/adapter.py` | WebSocket bridge integration |
| `runtime.py` | `AgentRuntime` orchestrator |

### BrowserEnvironment (client)

`fake-store/lib/agent/browser-environment.ts` implements:

- `observe()` — page context + optional screenshot
- `click()`, `type()`, `scroll()`, `navigate()`, `wait()`
- Target resolver with semantic ranking (no random DOM walks)

`FakeStoreEnvironment` is one adapter; Chrome extension and remote browsers use the same interface later.

### Protocol

Canonical schema: `shared/protocol/v2.schema.json`

Wire messages remain compatible with V1 `NEXT_ACTION` / `ACTION_RESULT` during migration. New field: `runtimePhase` on `NEXT_ACTION` for overlay states.

### Enable V2

```bash
# .env — V2 is default when unset
AGENT_RUNTIME_V2=true
```

Set `AGENT_RUNTIME_V2=false` to fall back to V1.

### SDK trajectory

```
@razorflow/protocol  ← generated from shared/protocol/v2.schema.json
@razorflow/core      ← agent_runtime (Python) / TS port
@razorflow/client    ← useAgentBridge + BrowserEnvironment
```

V2 runtime has **no** fake-store imports. Store hints (`data-rf-*`) are consumed only by the client observation layer as optional semantic signals.

## Design invariants

1. LLM proposes actions; verifier approves completion.
2. Execute → observe → verify after every meaningful action.
3. Never repeat a failed action signature without a new strategy.
4. Handoff preserves full run state; resume continues, not restarts.
5. No store-specific planning on the server.
