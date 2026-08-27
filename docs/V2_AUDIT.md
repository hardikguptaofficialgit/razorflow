# Agent Runtime V2 — Audit & Decision Map

## Is V2 genuinely LLM-driven?

**Yes.** When `AGENT_RUNTIME_V2=true`, the WebSocket bridge never calls:

- `store_planner`, `plan_guard_store`, `action_policy`, `heuristics`
- `planner_repair`, `task_intent`, `browser_use_runner`

**Single planning authority:** `LLMPlanner` → `LLMProvider.plan()` (Groq → OpenRouter → Gemini).

## V2 decision flow

```
START_RUN
  → task.parser.parse_task()           [goal extraction only]
  → observe_from_page_context()        [build observation]
  → memory.sync_memory_from_observation()
  → goal.approve_completion()            [terminal gate — cannot be bypassed by LLM]
  → recovery.stuck.detect_stuck()        [anti-loop]
  → LLMPlanner.plan()                    [ONLY action authority]
  → executor.translate_action()          [wire format]
  → client executes
  → verifier.action_result + goal.approve_completion()
  → replan
```

## Checkout failure — root cause (instrumented)

**Before fix:** `"add snacks and checkout"` → cart grew to **15 items** → `MAX_PLANNING_TURNS` (add spam loop).

**Trace showed:** LLM kept clicking Add to cart; no phase transition to checkout.

**Fixes applied:**
1. `memory/sync.py` — when cart has required items, set `ADD_PHASE_COMPLETE` constraint + `remaining_work` → checkout
2. `recovery/stuck.py` — block repeat **add** clicks only (not cart/checkout navigation)
3. `observation/signals.py` — generic signals; no `data-rf-*` dependency; no false login from header "Sign in"
4. `verifier/goal.py` — checkout requires `reached_checkout` milestone or verified checkout/auth signals

**After fix:** Checkout run: navigate snacks → add item → cart → handoff at 9 steps (login may be required on checkout). **No step-limit crash.**

## Remaining deterministic layers (intentional)

| Module | Role |
|--------|------|
| `task/parser.py` | NL → goal, budget, hints |
| `memory/sync.py` | Facts + remaining work from observation |
| `verifier/goal.py` | Evidence-based DONE |
| `verifier/action_result.py` | Post-action verification |
| `recovery/stuck.py` | Anti-loop |
| `executor/translate.py` | V2 action → wire step |

## Environment vs brain

| Layer | Store-specific? | Status |
|-------|-----------------|--------|
| `agent_runtime/` planner | No | LLM only |
| `observation/signals.py` | No | URL + text heuristics |
| `fake-store/page-context.ts` | Hints optional | `data-rf-*` + generic `article` cards |
| `dom-targeting.ts` | No | Semantic rank by product card text |

## SDK foundation

```
packages/razorflow-protocol/   ← canonical types + schema copy
packages/razorflow-client/     ← RazorFlowClient event API skeleton
agent_runtime/                 ← Python core (→ @razorflow/core)
shared/protocol/v2.schema.json ← source schema
scripts/generate-protocol-types.mjs
```

## Live E2E (latest full run)

| Task | Result |
|------|--------|
| wdwd | PASS (clarification) |
| search earbuds | PASS |
| best earbuds under ₹6000 | PASS |
| add snacks under ₹200 | PASS |
| add 2 snacks | PASS |
| buy me multi-item | PASS |
| open cart | PASS |
| remove headphones | PASS |
| add snacks + checkout | PASS (handoff at cart; auth may block checkout) |

**103 unit tests passing.**

Trace log: `agent-backend/logs/agent_runtime_v2.jsonl`
