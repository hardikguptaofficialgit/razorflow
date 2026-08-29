#!/usr/bin/env bash
set -euo pipefail

pytest -m "not legacy" \
  --ignore=tests/agent/test_dom_recovery_e2e.py \
  --ignore=tests/agent/test_target_resolution_20_buttons.py \
  --ignore=tests/agent/test_ws_stability.py \
  --ignore=tests/agent/test_e2e_browser_use_smoke.py \
  --ignore=tests/agent/test_e2e_scenarios.py \
  --ignore=tests/agent/test_store_dom_integration.py \
  --ignore=tests/agent/test_llm_failure_e2e.py \
  "$@"
