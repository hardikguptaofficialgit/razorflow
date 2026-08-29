/**
 * Mock WebSocket integration test — exercises real RazorFlow client lifecycle
 * against an in-process transport (no demo API).
 */

import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const clientDist = join(root, "packages", "razorflow-client", "dist", "index.js");

const {
  RazorFlow,
  RazorFlowError,
} = await import(pathToFileURL(clientDist).href);

class MockTransport {
  constructor() {
    this.handlers = new Set();
    this.connectionHandlers = new Set();
    this.sent = [];
    this.connected = false;
    this.server = null;
  }

  async connect() {
    this.connected = true;
    for (const h of this.connectionHandlers) h(true);
  }

  disconnect() {
    this.connected = false;
    for (const h of this.connectionHandlers) h(false);
  }

  send(message) {
    if (!this.connected) {
      throw new RazorFlowError("TRANSPORT_DISCONNECTED", "not connected");
    }
    this.sent.push(message);
    this.server?.(message, (reply) => this.receive(reply));
  }

  receive(message) {
    for (const h of this.handlers) h(message);
  }

  onMessage(handler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onConnectionChange(handler) {
    this.connectionHandlers.add(handler);
    return () => this.connectionHandlers.delete(handler);
  }

  isConnected() {
    return this.connected;
  }
}

class MockEnvironment {
  constructor() {
    this.executed = [];
  }

  async observeWire() {
    return {
      title: "Example",
      url: "https://example.com",
      elements: [
        {
          index: 1,
          role: "button",
          tag: "button",
          text: "Save",
          placeholder: null,
          ariaLabel: null,
        },
      ],
      products: [],
      cartLines: [],
    };
  }

  async executeStep(step, onProgress) {
    this.executed.push(step);
    onProgress?.(`execute ${step.action}`);
    return { success: true, verified: true };
  }
}

function wireServer(runId) {
  let turn = 0;
  return (message, reply) => {
    if (message.type === "START_RUN") {
      assert.equal(message.runId, runId);
      assert.match(message.task, /save/i);
      reply({
        type: "NEXT_ACTION",
        runId,
        turn: ++turn,
        steps: [
          {
            action: "click_element",
            role: "button",
            elementIndex: 1,
            matchText: "Save",
          },
        ],
        actionSummary: "click Save",
        chatMessage: "Clicking save",
        runtimePhase: "acting",
      });
      return;
    }
    if (message.type === "ACTION_RESULT") {
      assert.equal(message.success, true);
      reply({ type: "RUN_COMPLETE", runId, message: "Saved successfully." });
    }
  };
}

describe("RazorFlow SDK integration (mock transport)", () => {
  let transport;
  let environment;

  beforeEach(() => {
    transport = new MockTransport();
    environment = new MockEnvironment();
  });

  it("runs task → streams events → completes with trace", async () => {
    const runId = "run-mock-1";
    transport.server = wireServer(runId);

    const events = [];
    const client = new RazorFlow({
      endpoint: "ws://mock",
      transport,
      environment,
      autoConnect: false,
    });

    client.on("run_started", (p) => events.push(["run_started", p.runId]));
    client.on("action_started", (p) => events.push(["action_started", p.summary]));
    client.on("action_completed", (p) => events.push(["action_completed", p.success]));
    client.on("completed", (p) => events.push(["completed", p.message]));

    await client.connect();
    const run = await client.run({ task: "Click the Save button", runId });
    const result = await run.untilComplete({ timeoutMs: 5_000 });

    assert.equal(result.status, "completed");
    assert.equal(result.message, "Saved successfully.");
    assert.ok(result.trace.steps.length >= 3);
    assert.equal(environment.executed.length, 1);
    assert.equal(environment.executed[0].action, "click_element");
    assert.ok(events.some(([kind]) => kind === "completed"));
    assert.ok(transport.sent.some((m) => m.type === "START_RUN"));
    assert.ok(transport.sent.some((m) => m.type === "ACTION_RESULT"));
  });

  it("surfaces handoff from server", async () => {
    const runId = "run-handoff";
    transport.server = (message, reply) => {
      if (message.type === "START_RUN") {
        reply({
          type: "RUN_WAITING_FOR_USER",
          runId,
          message: "Complete login, then resume.",
        });
      }
    };

    const client = new RazorFlow({
      endpoint: "ws://mock",
      transport,
      environment,
      autoConnect: false,
    });
    await client.connect();
    const run = await client.run({ task: "Sign in to the portal", runId });
    const result = await run.untilComplete({ timeoutMs: 5_000 });
    assert.equal(result.status, "handoff");
    assert.match(result.message ?? "", /login/i);
  });

  it("throws RazorFlowError on transport disconnect during send", async () => {
    const client = new RazorFlow({
      endpoint: "ws://mock",
      transport,
      environment,
      autoConnect: false,
    });
    assert.throws(
      () => transport.send({ type: "CANCEL_RUN", runId: "x" }),
      (err) => err instanceof RazorFlowError && err.code === "TRANSPORT_DISCONNECTED",
    );
    await client.connect();
    assert.doesNotThrow(() =>
      transport.send({ type: "CANCEL_RUN", runId: "x" }),
    );
  });
});
