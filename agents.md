# AGENTS.md — RazorFlow

## Project Overview

RazorFlow is an AI browser agent (Chrome extension) that autonomously navigates e-commerce websites on behalf of a user — searching, comparing, adding to cart, and completing checkout via Razorpay test-mode APIs. It pauses for human input (e.g., login) and resumes on command. Built for the Razorpay AI Buildathon 2026, Track 01 (AI Growth & Agentic Commerce).

## Core Principles for AI Coding Agents (Cursor / Claude / Copilot)

Any AI agent (or human) contributing code to this repo MUST follow these rules:

1. **No unnecessary or oversized code blocks.** Write only the code needed to solve the task at hand. Do not generate speculative features, unused abstractions, or filler code "just in case."
2. **Follow the existing project structure.** Place new files in the correct directory (see Project Structure below). Never create new top-level folders without explicit reason.
3. **Reuse before creating.** Before writing a new function, utility, hook, or component, search the codebase for an existing one that does the same or similar job. Extend or reuse it instead of duplicating logic.
4. **No duplicate functionality.** If similar logic exists in two places, refactor into a shared utility rather than copy-pasting.
5. **Modular and single-responsibility.** Each file/function should do one thing well. Split large files (>200-300 lines) into smaller, composable modules.
6. **Readable over clever.** Prefer clear variable names and straightforward logic over dense one-liners or premature optimization.
7. **Consistent style.** Follow the linter/formatter config already in the repo (ESLint/Prettier for JS/TS, Black/Ruff for Python). Do not introduce a new style.
8. **Comment only when necessary.** Explain *why*, not *what*, and only for non-obvious logic. Do not narrate obvious code.
9. **Type safety.** Use TypeScript types / Python type hints for all new functions and interfaces. No implicit `any`.
10. **Scalable by default.** Design components/functions so they can be extended later (e.g., adding a new merchant, a new voice provider) without rewriting core logic.
11. **Test critical logic.** Any function touching money, cart state, or agent decision-making should have at least a basic unit test.
12. **Small, reviewable diffs.** Prefer several small, focused commits/PRs over one giant change.

## Project Structure

```
razorflow/
├── extension/              # Chrome extension (Manifest V3)
│   ├── background/         # Service worker: orchestration, messaging
│   ├── content/            # Content scripts: cursor overlay, DOM highlight, injection
│   ├── popup/               # Extension popup UI (React)
│   └── shared/              # Shared types/constants between background & content
├── agent-backend/          # Python backend (browser-use + LLM agent logic)
│   ├── core/                # Agent orchestration, task planning
│   ├── actions/             # Reusable browser actions (click, type, scroll, search)
│   ├── policy/               # Safety/spend-limit gate + Razorpay MCP client
│   ├── voice/                # Deepgram STT/TTS integration
│   └── utils/                # Shared helpers (logging, retries, config)
├── fake-store/              # Next.js demo e-commerce site
│   ├── app/                  # Pages: home, search, product, cart, checkout, login
│   ├── components/           # Reusable UI components (ProductCard, CartItem, etc.)
│   ├── lib/                  # Razorpay integration, catalog data access
│   └── data/                  # Seed product data
├── shared/                   # Cross-project shared types/schemas (if needed)
├── tests/                     # Unit and integration tests, mirrors src structure
└── docs/                       # Architecture diagrams, audit trail examples, README assets
```

## Architecture Rules

- **LLM never touches payments directly.** The agent proposes actions/carts only. A deterministic policy layer (agent-backend/policy/) validates price, stock, and spend limits before any Razorpay call executes.
- **Every money-related action must be logged.** Write to an append-only audit log (proposal → policy decision → execution result) for every checkout attempt.
- **Pause/resume must be a first-class state**, not a hack. The agent's task state machine must support: RUNNING → WAITING_FOR_USER → RUNNING, with the exact DOM/task context preserved across the pause.
- **Cursor overlay logic lives only in `extension/content/`.** Do not duplicate animation/highlight code inside the popup or background scripts.

## Razorpay MCP Integration

RazorFlow uses Razorpay's official MCP (Model Context Protocol) server as the execution layer for all payment-related actions. This replaces custom Razorpay SDK wrapper code and gives the agent standardized, well-documented tools for payments, orders, payment links, and refunds.

### Rules for MCP Usage

1. **The LLM/agent never calls MCP tools directly.** All Razorpay MCP tool calls must be routed through `agent-backend/policy/` after validation (price re-check, stock check, spend-limit check, idempotency key generation).
2. **Use the Remote MCP Server for development:** `https://mcp.razorpay.com/mcp` — zero setup, fastest for hackathon iteration.
3. **Switch to Local MCP Server (Docker) only if a required tool is restricted on remote** (e.g., refunds, settlements).
4. **Test-mode keys only.** Never commit live Razorpay keys. Use `.env` + `.env.example`, and add `.env` to `.gitignore`.
5. **Every MCP tool call must be logged** to the audit trail (`agent-backend/policy/audit_log.py` or equivalent) with: input proposal, policy decision, MCP tool + params called, and the result returned.
6. **Wrap MCP calls in a single reusable client module** (`agent-backend/policy/razorpay_mcp_client.py`). Do not call the MCP server from multiple places in the codebase — all payment execution goes through this one module.
7. **Handle MCP failures gracefully.** Any MCP call must have error handling and a defined fallback/retry policy — do not let a failed payment call silently disappear; log it and surface it to the audit trail and, if needed, the user.

### MCP Setup Checklist

- [ ] Add Razorpay test-mode API keys to `.env`
- [ ] Configure MCP client connection (`https://mcp.razorpay.com/mcp`) in `agent-backend/policy/razorpay_mcp_client.py`
- [ ] Verify connection by listing available MCP tools before building on top of it
- [ ] Confirm test-mode payment link/order creation works end-to-end before wiring into the full agent flow

## Before Submitting Code

- [ ] Did I reuse an existing utility/component instead of writing a new one?
- [ ] Is this file in the correct directory per the structure above?
- [ ] Is any function longer than ~50 lines? If so, can it be split?
- [ ] Did I add types/type hints?
- [ ] Did I avoid copy-pasting logic that exists elsewhere?
- [ ] Does this touch money/cart/agent-decision logic? If so, is there a test?
## Git Commit Discipline

After completing a meaningful, tested unit of work, create a Git commit.

A meaningful unit of work is a coherent milestone such as:
- Adding a complete feature.
- Completing an integration.
- Finishing a modular refactor.
- Fixing a bug with tests.
- Completing a well-defined project phase.

Before committing:

1. Review the changed files and remove accidental, generated, temporary, or unrelated files.
2. Run the relevant build, lint, type-check, and tests.
3. Confirm that secrets, API keys, `.env` files, credentials, and personal data are not included.
4. Review the final diff with `git diff`.
5. Do not commit broken, untested, or unrelated changes.

Use a concise Conventional Commit message:

```text
<type>(<scope>): <short description>
```

Allowed types include:
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — code restructuring without behavior change
- `test` — tests
- `docs` — documentation
- `chore` — maintenance/configuration

Examples:

```text
feat(extension): add DOM action playback
feat(backend): add Groq planner bridge
fix(extension): handle missing content script
test(policy): cover spend limit validation
docs: update local development setup
```

Do not create a commit after every tiny edit. Group related changes into a clean, reviewable milestone. Do not push to a remote repository unless explicitly instructed by the user.

After committing, report:
- Commit hash.
- Commit message.
- Files included.
- Validation commands run and their results.