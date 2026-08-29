# @hardik21232323/razorflow-client

RazorFlow Agent SDK — natural-language browser automation.

```typescript
import { RazorFlow } from "@hardik21232323/razorflow-client";

const agent = new RazorFlow({
  endpoint: "ws://127.0.0.1:8765/ws",
  environment: myBrowserEnvironment,
});

const run = await agent.run({ task: "Find the best option and add it to cart" });
```
