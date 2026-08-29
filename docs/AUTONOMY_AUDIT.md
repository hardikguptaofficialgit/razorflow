# RazorFlow Agent Runtime V2 — Final Autonomy Audit

**Date:** 2026-08-28  
**Scope:** Compare RazorFlow V2 against Browser Use, BrowserCode, BrowserGym, and Skyvern.  
**Purpose:** Decide whether Runtime V2 is ready to freeze.  
**Method:** Code review + reference-project concept mapping + live stress benchmark (not unit tests).

RazorFlow is **not** a general-purpose web automation framework. It is an **extension-backed autonomous shopping agent** with deterministic verification, phase-gated intents, and LLM short-horizon planning. Comparisons below account for that scope.

---

## Reference Projects (conceptual only — not installed)

| Project | Core model | RazorFlow overlap |
|---------|------------|-------------------|
| [Browser Use](https://github.com/browser-use/browser-use) | Playwright + LLM loop, DOM serializer + optional vision, 45+ actions, loop detector | Closest architectural cousin |
| [BrowserCode](https://github.com/browser-use/browsercode) | CDP-direct browser control, persistent sessions | RazorFlow uses extension DOM, not CDP |
| [BrowserGym](https://github.com/ServiceNow/BrowserGym) | Gym env, AXTree + DOM + screenshots, benchmark harness | RazorFlow has ad-hoc E2E, not gym API |
| [Skyvern](https://github.com/skyvern-ai/skyvern) | Vision-first, selector-free, cloud browser + workflow builder | RazorFlow is DOM-text, not vision-primary |

---

## Capability Matrix

| Capability | RazorFlow V2 | Browser Use | BrowserGym | Skyvern | Status |
|------------|--------------|-------------|------------|---------|--------|
| **Browser observation** | Extension `PageContext`: ranked elements, products, cart, signals, optional screenshot passthrough | DOM serializer + screenshot + recent events | Full DOM, AXTree, tabs, error feedback | Screenshot + simplified DOM tree | **PARTIAL** — no AXTree, capped lists (120 el / 32 products) |
| **DOM / semantic representation** | Element IDs (`e1`…), product rows, text/role/href blobs | Indexed interactive map, scrollable-container exceptions | `bid` identifiers, spatial coords | Vision + DOM fusion | **PARTIAL** — semantic enough for e-commerce, not arbitrary sites |
| **Visual understanding** | Screenshot in protocol; planner can receive it; **not used for targeting** | `use_vision` first-class, GPT-4V routing | Screenshot modality in obs space | Vision-primary element ID | **MISSING** for arbitrary visual UIs — **NOT NEEDED** for current shopping scope |
| **Target resolution** | Dual: server `refresh_action_target()` + client `findByRole`/`matchText`; product-title matching | Index-based + hash loop detection | `click(bid)` | Vision locate | **IMPLEMENTED** for extension-harvested pages |
| **Action space** | click, type/search, navigate, scroll, wait, go_back, handoff, finish | 45+ (tabs, upload, extract, select, …) | High-level + raw Playwright code mode | click, fill, select, scroll, upload | **PARTIAL** — no select/dropdown, tabs, file upload, extract |
| **Planning loop** | OBSERVE→PLAN(1–3)→ACT→VERIFY→RECOVER; runtime owns completion | step() loop, multi-action per step | env.step(action) | Task agent loop | **IMPLEMENTED** (shopping-biased) |
| **Short-horizon tasks** | Single search, single add, open cart | General | Benchmark tasks | Single prompts | **IMPLEMENTED** |
| **Long-horizon tasks** | Multi-item via `remaining_items` + phase machine; max ~16 planning turns | `max_steps` configurable, file memory | Multi-step benchmarks | Workflow blocks + agents | **PARTIAL** — works for 3-item cart, not arbitrary 20-step workflows |
| **Memory / state** | `TaskMemory`, milestones, action_history, metrics fingerprints | AgentHistoryList, MessageManager | Episode state | Workflow memory + credentials | **IMPLEMENTED** for run-scoped tasks |
| **Recovery** | stuck.py, loop_detector, planner nudges, parse/empty-plan retry | Loop nudges, exploration nudges | Error in next observation | Re-plan on failure | **IMPLEMENTED** |
| **Retries** | Consecutive failure nudges; extension retry once on connection loss; max 8 failures | `max_failures`, step timeout | Implicit via agent | Step-level retry | **IMPLEMENTED** |
| **Loop prevention** | Action hash window + page stagnation fingerprints | ActionLoopDetector + stagnant pages | N/A (eval metric) | Reflection | **IMPLEMENTED** |
| **Page change handling** | `BrowserPage.signature()` with element sample; re-observe after act | Full state diff | POMDP observation update | Re-screenshot each step | **IMPLEMENTED** |
| **Scrolling** | `scroll_page` (up/down/top/bottom) + scrollIntoView on element | scroll actions | scroll primitives | scroll in action set | **IMPLEMENTED** |
| **Waiting** | `wait` 100–5000ms | wait action | sleep in code mode | implicit in steps | **IMPLEMENTED** |
| **Navigation** | `navigate_url` | goto, tabs | navigate, tab_* | navigate | **PARTIAL** — no multi-tab |
| **Backtracking** | `go_back` via history | back action | go_back | implicit | **IMPLEMENTED** (basic) |
| **Task completion verification** | `approve_completion()` — runtime gates, not LLM `finish` | `validate_output`, done action reviewed | Reward / success criteria | Extraction schema | **IMPLEMENTED** — strongest RazorFlow differentiator |
| **Human handoff** | Policy-gated: login, OTP, CAPTCHA, checkout auth — not uncertainty | User takeover hooks | `send_msg_to_user` | Credential login blocks | **IMPLEMENTED** |
| **Browser / session management** | Per-run `RunState`; extension tab; bridge `RunManager` | BrowserSession, persistent contexts | Gym env lifecycle | Cloud sessions 24h | **PARTIAL** — single tab, no cross-run persistence |
| **Evaluation** | Real UI suite, 20-button, DOM/LLM E2E, stress benchmark | Built-in history GIF, tracing | Standardized benchmarks (WebArena, WorkArena, …) | Cloud run summaries | **PARTIAL** — no public benchmark suite |

---

## RazorFlow-Specific Strengths (vs references)

1. **Verifier-owned completion** — LLM `proposeFinish` cannot complete without `approve_completion()`. Browser Use/Skyvern lean more on model-declared done.
2. **Phase action gate** — Prevents intent escalation (search→buy, add→checkout) without explicit user goal.
3. **Dual target resolution** — Planner IDs re-matched server-side before dispatch; client re-resolves at execution.
4. **Checkout/login handoff** — Generic `checkout_flow.py` detects auth gates without hardcoding store routes.

---

## Gaps That Matter for *Arbitrary* Browser Tasks

| Gap | Severity for RazorFlow today | Implement now? |
|-----|---------------------------|----------------|
| Vision-based element locate | High for unknown sites | **No** — out of shopping scope; SDK phase |
| CDP / Playwright direct control | High for non-DOM apps | **No** — extension model is intentional |
| `select` / dropdown / file upload | Medium | **No** — not required for demo store flows |
| Multi-tab workflows | Medium | **No** |
| Cross-run session persistence | Low | **No** |
| Standardized benchmark harness (BrowserGym-style) | Low for product | **No** — stress benchmark sufficient for freeze |

**Conclusion:** No **critical** missing capability blocks freezing V2 for its designed scope (autonomous shopping via extension on structured e-commerce pages).

---

## Gaps Explicitly NOT NEEDED (for V2 freeze)

- Workflow builder / no-code editor (Skyvern Cloud)
- 45+ action registry (Browser Use)
- Raw Python Playwright code mode (BrowserGym)
- Docker cloud browser farm (Skyvern)
- Site-specific XPath libraries

---

## Architecture Freeze Boundary

**Frozen (do not rewrite):**
- `agent_runtime/runtime.py` observe→plan→act→verify loop
- `verifier/goal.py` completion ownership
- `policy/action_gate.py` phase gates
- Extension DOM execution path
- Single LLM planner (`LLMPlanner`)

**Allowed post-freeze (bugfixes only):**
- Observation caps, timeout tuning
- Planner prompt wording
- Trace/logging
- Test harnesses

---

## Stress Benchmark Results (2026-08-28, post-autonomy pass)

**Harness:** `tests/agent/run_autonomy_stress_benchmark.py` → `tests/agent/autonomy_stress_results.json`  
**Method:** Real Chromium + WebSocket runtime (no extension UI). Fake-store tasks use generic DOM harness; fixture tasks use adversarial HTML.

| Task | Result | Steps | LLM | Recovery | Notes |
|------|--------|-------|-----|----------|-------|
| Find cheapest smartwatch | **PASS** | 1 | 2 | 0 | Search with `?q=smartwatch`, no cart escalation |
| Snack under ₹200, inspect best | **PASS** | 1 | 2 | 0 | Search results only, no add/checkout |
| Compare earbuds, add best | **PASS** | 2 | 4 | 0 | Search → single add, cart=1 |
| 20-button Galaxy Buds FE | **PASS** | 1 | 2 | 0 | Correct product |
| 20-button Amul Butter | **PASS** | 1 | 2 | 0 | Correct product |
| DOM disappear recovery | **PASS** | 4 | 26 | 14 | Replanned after DOM loss; no false DONE |
| Scroll + add cooker | **PASS** | 1 | 2 | 0 | On-page find + single add |

**Aggregate:** **7/7 (100%)** success rate · 40 LLM calls · 14 recovery events · 0 loop-driven failures  
**Safety:** 0 wrong-target · 0 false completion · 0 false handoff  
**Avg latency:** ~10s/task (down from ~26s pre-fix)

**Real UI regression (extension path):** **10/10** — including checkout multi-phase and compare+add best.

### Subsystems fixed (generic, not per-task)

| Subsystem | Fix |
|-----------|-----|
| **Goal guard** | Block actions that don't advance remaining work; stop find/inspect when search satisfied; quota enforcement |
| **Search state** | Token-based entity↔URL matching; distinguish browse vs search; `needs_search` when query missing from URL |
| **Task parsing** | Compare+add entity extraction; checkout multi-phase; submit-order vs purchase |
| **Phase-aware prompts** | `forbidden_now` / `checkout_allowed` derived from `current_phase`, not parse-time snapshot |
| **Verification** | Accept URL/DOM evidence when harness reports `success: false`; scroll no longer false-positive |
| **Goal completion** | Find tasks require entity in search URL before `approve_completion()` |
| **WS harness** | React controlled-input setter for search submit; navigation-context retry |

**Prior run (pre-fix):** 3/7 stress · Real UI 10/10 · failures were over-action, false completion on `/search` without query, compare entity parse bugs, checkout planner blocked by stale `forbidden_now`.

---

## Stress Benchmark Results (2026-08-28, initial audit — superseded)

<details>
<summary>Initial 3/7 run (historical)</summary>

| Task | Result | Steps | LLM | Recovery | Notes |
|------|--------|-------|-----|----------|-------|
| Find cheapest smartwatch | FAIL | 2 | 12 | 0 | RUN_ERROR after search scroll+type |
| Snack under ₹200, inspect best | FAIL | 1 | 10 | 0 | RUN_ERROR on `/search` |
| Compare earbuds, add best | FAIL | 6 | 18 | 2 | cart=3 but RUN_ERROR (over-add, max turns) |
| 20-button Galaxy Buds FE | **PASS** | 1 | 2 | 0 | Correct product |
| 20-button Amul Butter | **PASS** | 1 | 2 | 0 | Correct product |
| DOM disappear recovery | **PASS** | 2 | 9 | 6 | No false DONE; replanned |
| Scroll + add cooker | FAIL | 10 | 20 | 9 | cart=8, repeated adds, no scroll |

**Aggregate:** 3/7 (43%) · 73 LLM calls · 17 recovery events
</details>

---

## Freeze Recommendation

**FREEZE Agent Runtime V2** — autonomy stress benchmark **7/7** and real UI regression **10/10** with zero safety violations (wrong-target, false completion, false handoff).

Confirmed on:
- autonomous workflow derivation (find / inspect / compare / add / checkout phases)
- 20-button disambiguation
- DOM disappearance recovery
- anti-escalation (no spurious cart/checkout on find-only goals)
- multi-phase checkout and compare+add flows

SDK/productization is the next phase and should not alter the frozen runtime contract.
