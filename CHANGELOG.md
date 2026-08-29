# Changelog

All notable changes to the RazorFlow SDK packages are documented here.

## [0.1.0] - 2026-08-30

### Added
- `@hardik21232323/razorflow-protocol` — wire types, observation schemas, traces, typed errors
- `@hardik21232323/razorflow-browser` — `BrowserEnvironment`, `DomBrowserEnvironment`, observation builders
- `@hardik21232323/razorflow-client` — `RazorFlow`, `AgentRun`, `WebSocketTransport`, event streaming, `untilComplete()`
- Mock WebSocket integration tests for full task lifecycle
- Generic agent runtime mode (`AGENT_SHOPPING_DOMAIN=false`) with dedicated test suite

### Changed
- Extension and fake-store consume protocol types from the SDK package (no duplicate wire schemas)
- Client reconnect uses exponential backoff (max 8 attempts)

### Notes
- Packages target the **real** RazorFlow WebSocket runtime (`/ws` on the agent backend)
- npm publish is configured but **0.1.0 has not been published** pending final validation
