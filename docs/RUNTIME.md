# Runtime versions

RazorFlow ships two agent runtimes. **Only V2 is supported for new work.**

## V2 — supported (`agent_runtime/`)

- **Entry:** `agent-backend/main.py` with `AGENT_RUNTIME_V2=true` (default in `.env.test`)
- **Architecture:** Domain-skill model — generic core + optional shopping skill (`AGENT_SHOPPING_DOMAIN`)
- **Tests:** `tests/agent/test_runtime_v2_*`, `test_generic_mode_runtime.py`, shopping/policy/voice suites
- **CI:** Release gate runs V2 + generic-mode tests via `scripts/ci-no-llm-pytest.sh`

## V1 — legacy / unsupported (`agent-backend/core/agent_loop.py`)

- **Status:** Frozen. No new features or bugfix investment unless blocking a demo.
- **Known gaps:** `core/agent_loop.py` planner path diverged from V2; several V1-only tests are marked `@pytest.mark.legacy` and excluded from CI.
- **Migration:** Use V2 runtime + extension DOM executor (`BROWSER_USE_EXECUTOR_ENABLED=false`).

## Environment flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_RUNTIME_V2` | `true` | Use `agent_runtime` loop (supported) |
| `AGENT_SHOPPING_DOMAIN` | `true` | Enable shopping skill; `false` = generic-only mode |
| `BROWSER_USE_EXECUTOR_ENABLED` | `false` | Extension executes DOM actions (recommended) |

## SDK

Published packages (install order): `@hardik21232323/razorflow-protocol` → `razorflow-browser` → `razorflow-client`.

See `packages/README.md` for build and publish commands.
