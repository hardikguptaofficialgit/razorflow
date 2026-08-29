# RazorFlow Agent Scorecard

**Date:** 2026-08-27  
**Phase:** Real browser execution + failure recovery + SDK readiness  
**Method:** Actual RazorFlow chat UI on `http://localhost:3001/demo` (Playwright). No benchmark harness bypass for real UI tasks.

---

## Executive summary

| Category | Passed | Total | Rate | Status |
|----------|--------|-------|------|--------|
| **Real UI (chat)** | 9 | 10 | 90% | **NOT COMPLETE** |
| Happy path (harness) | 9 | 12 | 75% | Regression |
| Adversarial unit | 24 | 24 | 100% | Pass |
| Adversarial live/generic | 4 | 4 | 100% | Pass |
| Handoff policy (unit) | 7 | 7 | 100% | Pass |
| Completion verification (unit) | 4 | 4 | 100% | Pass |
| LLM failure injection (unit) | 6 | 6 | 100% | Pass |
| Loop prevention (unit) | 2 | 2 | 100% | Pass |
| Target resolution (20 buttons) | 0 | 3 | 0% | **Blocked (infra)** |
| SDK readiness audit | — | — | — | **Ready (no publish)** |

**Phase acceptance:** **NOT MET** — checkout real-UI task failed; happy-path harness regressed; 20-button test not verified.

---

## 1. Real UI tasks (required)

Path: `tests/agent/run_real_ui_agent.py`  
Evidence: `tests/agent/real_ui_run.log`, `tests/agent/real_ui_results_remaining.json`

| # | Task | Result | Duration | Final URL | Handoff | Trace |
|---|------|--------|----------|-----------|---------|-------|
| 1 | search for wireless earbuds | **PASS** | 13.4s | `/demo/search?q=earbuds` | No | 6 entries |
| 2 | find good wireless earbuds under ₹6000 | **PASS** | 17.2s | `/demo/search?q=earbuds` | No | 6 entries |
| 3 | add good snacks under ₹200 to my cart | **PASS** | 11.0s | `/demo` (cart=1) | No | 6 entries |
| 4 | add the best cooker under ₹2000 to my cart | **PASS** | 33.6s | `/demo/search?q=cooker` (cart=1) | No | 12 entries |
| 5 | add butter, chips and cooker to my cart | **PASS** | 29.0s | `/demo` (cart=3) | No | 18 entries |
| 6 | open my cart | **PASS** | 11.5s | `/demo/cart` | No | 6 entries |
| 7 | remove the headphones from my cart | **PASS** | 24.9s | `/demo/cart` | No | 12 entries |
| 8 | add good snacks under ₹200 and checkout | **FAIL** | 111.8s | `/demo` (cart=1) | No | 84 entries |
| 9 | find the cheapest smartwatch | **PASS** | 17.2s | `/demo/search?q=smartwatch` | No | 6 entries |
| 10 | find wireless earbuds and add the best one to my cart | **PASS** | 42.0s | `/demo/search?q=earbuds` (cart=2) | No | 18 entries |

### Task 8 failure analysis

- **Subsystem:** `PLANNER` (+ `RECOVERY` — 84 executor traces, no checkout navigation)
- **Symptom:** Added snacks (cart=1) but never reached `/checkout` or login gate within 180s budget
- **Browser proof:** Execution traces show real `target_resolved` → `cursor_position` → `action_result` → `page_state` on home page only
- **Not:** false handoff, harness bypass, or mocked verifier

### Sample execution trace (task 1 — proves real executor)

```
action_start → type_in_element (search, "wireless earbuds")
page_state   → url=/demo cart=0
target_resolved → input[Search products] rect=(453,12,490×36)
cursor_position → (699,34) aligned to input center
action_result  → success=true verified=true
page_state   → url=/demo/search?q=earbuds cart=0
```

WebSocket flow: `START_RUN` → `NEXT_ACTION` → `ACTION_RESULT` → `RUN_COMPLETE`

---

## 2. Cursor validation

| Metric | Result |
|--------|--------|
| Cursor mismatches (threshold 80px) | **0** across all 9 passing tasks |
| Cursor independent targeting | **Not observed** — cursor follows `target_resolved` rect |
| Typing path | cursor → focus → type → verified URL/query change |

Instrumentation: `fake-store/lib/agent/execution-trace.ts` + `action-executor.ts`

---

## 3. Handoff validation

| Scenario | Expected | Result |
|----------|----------|--------|
| search earbuds | No handoff | **Pass** (real UI) |
| add snacks | No handoff | **Pass** |
| open cart | No handoff | **Pass** |
| find smartwatch | No handoff | **Pass** |
| LLM uncertainty reason | No handoff | **Pass** (unit) |
| click failure reason | No handoff | **Pass** (unit) |
| login / OTP / CAPTCHA / payment | Handoff allowed | **Pass** (unit) |

---

## 4. LLM failure injection (unit)

`tests/agent/test_llm_failure_injection.py` — **6/6 pass**

| Case | Behavior |
|------|----------|
| Invalid role `search/input` | Normalized to `search` (PARSER) |
| Invalid JSON | Raises `ValueError` |
| Role aliases (searchbox, textbox, button/link) | Normalized |
| Hallucinated element in runtime | Dispatches continue (recovery path) |

Runtime parse recovery added in `agent_runtime/planner/llm_provider.py` + `runtime.py` (`planner_parse_retries`).

---

## 5. Loop / oscillation (unit)

`tests/agent/test_loop_oscillation.py` — **2/2 pass**

- Repeated failed action → blocked signature + recovery nudge
- A↔B oscillation → detected

---

## 6. Completion verification (unit)

`tests/agent/test_completion_verification.py` — **4/4 pass**

- LLM `DONE` on home page for search → **rejected**
- Search results page → **approved**
- Cart visible for "open my cart" → **approved**
- Add-to-cart goal on search-only page → **not satisfied**

---

## 7. Target resolution — 20 identical buttons

`tests/agent/fixtures/target_resolution_page.html` + `tests/agent/test_target_resolution_20_buttons.py`

| Result | Notes |
|--------|-------|
| **0/3** | WebSocket backend timeouts during test run (keepalive ping timeout / handshake timeout). **Not a confirmed wrong-click failure** — infra blocked verification. |

**Action required:** Re-run with isolated backend; confirm `data-product-id` on clicked button.

---

## 8. Happy path & adversarial benchmarks

| Suite | Score | Notes |
|-------|-------|-------|
| Happy path harness | **9/12 (75%)** | Regressed: cooker phrasing, checkout combo, "buy snacks" |
| Adversarial unit | **24/24** | Stable |
| Adversarial live/generic | **4/4** | Stable |
| Parser/verifier/entity unit | **26/26** | Stable |

---

## 9. Performance (real UI, measure only)

| Task | Total | LLM cycles (approx) | Browser actions (trace) | Failed actions | Recoveries |
|------|-------|---------------------|-------------------------|----------------|------------|
| search earbuds | 13.4s | 1 | 1 | 0 | 0 |
| earbuds under ₹6000 | 17.2s | 1 | 1 | 0 | 0 |
| add snacks | 11.0s | 1 | 1 | 0 | 0 |
| best cooker | 33.6s | 2 | 2 | 0 | 0 |
| butter+chips+cooker | 29.0s | 3 | 3 | 0 | 0 |
| open cart | 11.5s | 1 | 1 | 0 | 0 |
| remove headphones | 24.9s | 2 | 2 | 0 | 0 |
| **checkout combo** | **111.8s** | **many** | **42** | **unknown** | **high** |
| cheapest smartwatch | 17.2s | 1 | 1 | 0 | 0 |
| earbuds + add best | 42.0s | 3 | 3 | 0 | 0 |

**Bottleneck:** Multi-phase goals (add + checkout) trigger excessive replanning on home page. Simple search tasks complete in **1 LLM cycle / 1 action (~11–17s)**.

---

## 10. SDK readiness audit

| Package | Fake-store dep | React dep | Ecommerce terms | Planner leak | Verdict |
|---------|----------------|-----------|-----------------|--------------|---------|
| `razorflow-protocol` | No | No | Comment only (generic observation) | No | **Ready** |
| `razorflow-client` | No | No | No | No | **Ready** |
| `razorflow-browser` | Comment only (env examples) | No | No | No | **Ready** |

Exposed concepts match target: `RazorFlow`, `AgentRun`, `Transport`, `BrowserEnvironment`, events (`action_started`, `verification`, `handoff`, `completed`, `failed`).

**Do not publish npm yet** — real UI phase incomplete.

---

## 11. Fixes landed this phase

1. **`execution-trace.ts`** — runtime proof of target/cursor/page state
2. **`run_real_ui_agent.py`** — real chat UI harness (React controlled input, Playwright WS monitor, no WS monkey-patch)
3. **`llm_provider.py`** — role normalization (`search/input` → `search`)
4. **`runtime.py`** — planner parse recovery (invalid schema → retry, not silent DONE)
5. Unit suites: handoff, completion, loop, LLM failure injection

---

## 12. Known failures (do not hide)

| ID | Subsystem | Issue |
|----|-----------|-------|
| RUI-08 | PLANNER | Checkout combo stops after add; 84 actions without `/checkout` |
| HP-09 | PLANNER/PARSER | Harness happy-path regressed to 9/12 |
| TR-20 | TRANSPORT | 20-button test blocked by WS timeouts |

---

## 13. Next steps (before SDK productization)

1. Fix checkout goal phase: after `cart_updated`, planner must allow `cart_nav` / checkout navigation (PLANNER + ACTION_GATE)
2. Re-run `test_target_resolution_20_buttons.py` with dedicated backend
3. Re-run full `run_real_ui_agent.py` until **10/10**
4. Restore happy-path harness to **12/12**
