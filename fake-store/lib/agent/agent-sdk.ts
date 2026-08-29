/**
 * RazorFlow SDK singleton for the embedded fake-store agent.
 * Lazy-init — only constructed in the browser.
 */

import { RazorFlow } from "@hardik21232323/razorflow-client";
import { fakeStoreEnvironment } from "@/lib/agent/fake-store-environment";
import { getBridgeWsUrl } from "@/lib/agent/bridge-protocol";

let client: RazorFlow | null = null;

export function getRazorFlowClient(): RazorFlow {
  if (typeof window === "undefined") {
    throw new Error("RazorFlow client is only available in the browser");
  }
  if (!client) {
    client = new RazorFlow({
      endpoint: getBridgeWsUrl(),
      environment: fakeStoreEnvironment,
      autoConnect: false,
    });
  }
  return client;
}
