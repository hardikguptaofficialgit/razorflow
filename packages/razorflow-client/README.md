# @hardik21232323/razorflow-client

RazorFlow Agent SDK — connect to the real agent runtime over WebSocket, submit natural-language tasks, stream events, and execute returned actions in your browser environment.

## Install

```bash
npm install @hardik21232323/razorflow-client @hardik21232323/razorflow-browser @hardik21232323/razorflow-protocol
```

## Quick start

```typescript
import { RazorFlow, DomBrowserEnvironment } from "@hardik21232323/razorflow-client";

const agent = new RazorFlow({
  endpoint: "ws://127.0.0.1:8765/ws",
  environment: new DomBrowserEnvironment(),
});

agent.on("action_started", ({ summary }) => console.log("→", summary));
agent.on("completed", ({ message }) => console.log("done", message));
agent.on("handoff", ({ message }) => console.log("needs user", message));

const run = await agent.run({ task: "Open the Travel category and open the first book" });
const result = await run.untilComplete({ timeoutMs: 120_000 });
console.log(result.status, result.trace.steps.length, "steps");
```

## API surface

| Export | Role |
|--------|------|
| `RazorFlow` | Connect, `run()`, event emitter |
| `AgentRun` | Per-run handle: `untilComplete()`, `cancel()`, `resume()`, `trace` |
| `WebSocketTransport` | Default WS transport (exponential backoff reconnect) |
| `DomBrowserEnvironment` | Reference DOM executor (click, type, scroll, wait, go_back) |
| `RazorFlowError` | Typed errors (`TRANSPORT_*`, `RUN_*`) |

## Events

`run_started` · `planning` · `action_started` · `action_completed` · `verification` · `recovery` · `agent_chat` · `handoff` · `completed` · `failed` · `agent_sync` · `payment_required` · `payment_ready`

## Custom environments

Implement `BrowserEnvironment` from `@hardik21232323/razorflow-browser` for Playwright, Chrome extension, or embedded apps. The SDK sends `START_RUN` + `pageContext`; the server replies with `NEXT_ACTION` steps your environment must execute, then you send `ACTION_RESULT`.

## Wire protocol

Message types (`START_RUN`, `NEXT_ACTION`, `ACTION_RESULT`, `RUN_COMPLETE`, …) and `ActionStep` variants are defined in `@hardik21232323/razorflow-protocol` and shared with the Chrome extension and agent backend.

## License

MIT — see [LICENSE](./LICENSE).
