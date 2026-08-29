/**
 * @razorflow/client — RazorFlow Agent SDK
 *
 * Architecture:
 *   RazorFlow → Transport → Agent Runtime (server)
 *                      ↘ BrowserEnvironment (local execution)
 */

import type {
  ActionStep,
  BrowserObservation,
  ClientToServerMessage,
  PageContextWire,
  PaymentLinkProposal,
  RunPhase,
  RunTrace,
  ServerToClientMessage,
  TraceStep,
} from "@hardik21232323/razorflow-protocol";
import { sanitizePageContextWire, RazorFlowError } from "@hardik21232323/razorflow-protocol";
import type { BrowserEnvironment } from "@hardik21232323/razorflow-browser";

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

export interface Transport {
  connect(): Promise<void>;
  disconnect(): void;
  send(message: ClientToServerMessage): void;
  onMessage(handler: (message: ServerToClientMessage) => void): () => void;
  onConnectionChange(handler: (connected: boolean) => void): () => void;
  isConnected(): boolean;
}

export class WebSocketTransport implements Transport {
  private ws: WebSocket | null = null;
  private readonly url: string;
  private readonly apiKey?: string;
  private messageHandlers = new Set<(m: ServerToClientMessage) => void>();
  private connectionHandlers = new Set<(c: boolean) => void>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 8;

  constructor(url: string, apiKey?: string) {
    this.url = url;
    this.apiKey = apiKey;
  }

  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }
    this.shouldReconnect = true;
    const wsUrl = this.apiKey
      ? `${this.url}${this.url.includes("?") ? "&" : "?"}apiKey=${encodeURIComponent(this.apiKey)}`
      : this.url;

    await new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      this.ws = ws;
      ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.notifyConnection(true);
        resolve();
      };
      ws.onerror = () =>
        reject(
          new RazorFlowError(
            "TRANSPORT_CONNECT_FAILED",
            "WebSocket connection failed",
          ),
        );
      ws.onclose = () => {
        this.notifyConnection(false);
        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          const delay = Math.min(30_000, 1000 * 2 ** this.reconnectAttempts);
          this.reconnectAttempts += 1;
          this.reconnectTimer = setTimeout(() => void this.connect().catch(() => {}), delay);
        }
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(String(event.data)) as ServerToClientMessage;
          for (const h of this.messageHandlers) {
            h(msg);
          }
        } catch {
          /* ignore */
        }
      };
    });
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.ws?.close();
    this.ws = null;
  }

  send(message: ClientToServerMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new RazorFlowError("TRANSPORT_DISCONNECTED", "Transport not connected");
    }
    this.ws.send(JSON.stringify(message));
  }

  onMessage(handler: (message: ServerToClientMessage) => void): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onConnectionChange(handler: (connected: boolean) => void): () => void {
    this.connectionHandlers.add(handler);
    return () => this.connectionHandlers.delete(handler);
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private notifyConnection(connected: boolean): void {
    for (const h of this.connectionHandlers) {
      h(connected);
    }
  }
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export type RazorFlowEventMap = {
  run_started: { runId: string; task: string };
  observing: { runId: string };
  planning: { runId: string };
  action_started: { runId: string; summary: string };
  action_completed: {
    runId: string;
    success: boolean;
    verified?: boolean;
    error?: string;
  };
  verification: {
    runId: string;
    success: boolean;
    verified?: boolean;
  };
  recovery: { runId: string; message: string };
  agent_chat: { runId: string; text: string };
  handoff: { runId: string; message: string };
  needs_clarification: { runId: string; message: string };
  payment_required: { runId: string; proposal: PaymentLinkProposal };
  payment_ready: {
    runId: string;
    url: string;
    amountPaise: number;
    currency: string;
  };
  completed: { runId: string; message?: string };
  failed: { runId: string; message: string };
  connection_change: { connected: boolean };
  agent_config_status: {
    mode: "server_default" | "byok";
    useByok: boolean;
    provider?: string;
    model?: string;
    temperature?: number;
    maxAgentSteps: number;
    shoppingSkillEnabled: boolean;
    message?: string;
  };
  agent_sync: {
    runId: string;
    phase: string;
    actionSummary: string;
    url: string;
    step: number;
    cursor?: { x: number; y: number };
    highlight?: { x: number; y: number; width: number; height: number };
  };
  executor_mode: { runId: string; mode: "extension_dom" | "browser_use" };
};

export type EventHandler<K extends keyof RazorFlowEventMap> = (
  payload: RazorFlowEventMap[K],
) => void;

// ---------------------------------------------------------------------------
// Run handle
// ---------------------------------------------------------------------------

export interface RunStatus {
  runId: string;
  task: string;
  phase: RunPhase;
  connected: boolean;
  error: string | null;
  waitingMessage: string | null;
}

export interface RunResult {
  runId: string;
  status: "completed" | "handoff" | "failed" | "cancelled";
  message?: string;
  trace: RunTrace;
}

export class AgentRun {
  readonly runId: string;
  readonly task: string;
  private readonly client: RazorFlow;
  private _phase: RunPhase = "idle";
  private _error: string | null = null;
  private _waitingMessage: string | null = null;
  private _trace: RunTrace;
  private _step = 0;
  private _startedAt = Date.now();
  private _processing = false;
  private _cancelled = false;
  private _actionQueue: ServerToClientMessage | null = null;

  constructor(runId: string, task: string, client: RazorFlow) {
    this.runId = runId;
    this.task = task;
    this.client = client;
    this._trace = {
      runId,
      task,
      startedAt: Date.now(),
      status: "observing",
      steps: [],
      metrics: {
        llmCalls: 0,
        actionsExecuted: 0,
        recoveries: 0,
        failedActions: 0,
        totalDurationMs: 0,
      },
    };
    this.pushTrace("run_started", "observing", { message: task });
  }

  get status(): RunStatus {
    return {
      runId: this.runId,
      task: this.task,
      phase: this._phase,
      connected: this.client.transport.isConnected(),
      error: this._error,
      waitingMessage: this._waitingMessage,
    };
  }

  get trace(): RunTrace {
    this._trace.metrics.totalDurationMs = Date.now() - this._startedAt;
    return { ...this._trace, steps: [...this._trace.steps] };
  }

  cancel(): void {
    this._cancelled = true;
    this._phase = "cancelled";
    this.client.transport.send({ type: "CANCEL_RUN", runId: this.runId });
    this.pushTrace("failed", "cancelled", { message: "Cancelled by user" });
  }

  async resume(): Promise<void> {
    this._cancelled = false;
    this._phase = "observing";
    this._waitingMessage = null;
    const pageContext = sanitizePageContextWire(
      (await this.client.environment.waitForStable?.()) ??
        (await this.client.environment.observeWire()),
    );
    this.client.transport.send({
      type: "RESUME_RUN",
      runId: this.runId,
      pageContext,
    });
    this.pushTrace("observing", "observing");
    this.client.emit("observing", { runId: this.runId });
  }

  confirmPayment(): void {
    this.client.transport.send({
      type: "CONFIRM_PAYMENT_LINK",
      runId: this.runId,
      confirmed: true,
    });
  }

  declinePayment(): void {
    this.client.transport.send({
      type: "DECLINE_PAYMENT_LINK",
      runId: this.runId,
    });
  }

  /**
   * Await terminal run outcome (completed, handoff, or failure).
   */
  untilComplete(options?: { timeoutMs?: number }): Promise<RunResult> {
    const timeoutMs = options?.timeoutMs ?? 300_000;
    return new Promise<RunResult>((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        reject(
          new RazorFlowError("RUN_TIMEOUT", "Run timed out", {
            runId: this.runId,
            recoverable: true,
          }),
        );
      }, timeoutMs);

      const finish = (result: RunResult) => {
        cleanup();
        resolve(result);
      };

      const fail = (message: string, recoverable = false) => {
        cleanup();
        reject(
          new RazorFlowError("RUN_FAILED", message, {
            runId: this.runId,
            recoverable,
          }),
        );
      };

      const offComplete = this.client.on("completed", (payload) => {
        if (payload.runId !== this.runId) {
          return;
        }
        finish({
          runId: this.runId,
          status: "completed",
          message: payload.message,
          trace: this.trace,
        });
      });
      const offHandoff = this.client.on("handoff", (payload) => {
        if (payload.runId !== this.runId) {
          return;
        }
        finish({
          runId: this.runId,
          status: "handoff",
          message: payload.message,
          trace: this.trace,
        });
      });
      const offFailed = this.client.on("failed", (payload) => {
        if (payload.runId !== this.runId) {
          return;
        }
        fail(payload.message);
      });
      const offClarify = this.client.on("needs_clarification", (payload) => {
        if (payload.runId !== this.runId) {
          return;
        }
        finish({
          runId: this.runId,
          status: "handoff",
          message: payload.message,
          trace: this.trace,
        });
      });

      const cleanup = () => {
        clearTimeout(timer);
        offComplete();
        offHandoff();
        offFailed();
        offClarify();
      };

      if (this._phase === "completed") {
        finish({ runId: this.runId, status: "completed", trace: this.trace });
      } else if (this._phase === "failed") {
        fail(this._error ?? "Run failed");
      } else if (this._phase === "handoff") {
        finish({
          runId: this.runId,
          status: "handoff",
          message: this._waitingMessage ?? undefined,
          trace: this.trace,
        });
      } else if (this._phase === "cancelled") {
        finish({ runId: this.runId, status: "cancelled", trace: this.trace });
      }
    });
  }

  /** @internal */
  handleServerMessage(message: ServerToClientMessage): void {
    if ("runId" in message && message.runId && message.runId !== this.runId) {
      return;
    }

    switch (message.type) {
      case "NEXT_ACTION":
        if ("chatMessage" in message && message.chatMessage) {
          this.client.emit("agent_chat", {
            runId: this.runId,
            text: message.chatMessage,
          });
        }
        this._actionQueue = message;
        void this.drainQueue();
        break;
      case "RUN_WAITING_FOR_USER":
        this._phase = "handoff";
        this._waitingMessage = message.message ?? "Waiting for user";
        this.pushTrace("handoff", "handoff", { message: this._waitingMessage });
        this.client.emit("handoff", {
          runId: this.runId,
          message: this._waitingMessage,
        });
        break;
      case "RUN_NEEDS_CLARIFICATION":
        this._phase = "handoff";
        this._waitingMessage = message.message;
        this.pushTrace("handoff", "handoff", { message: message.message });
        this.client.emit("needs_clarification", {
          runId: this.runId,
          message: message.message,
        });
        break;
      case "RUN_COMPLETE":
        this._phase = "completed";
        this._trace.endedAt = Date.now();
        this.pushTrace("completed", "completed", { message: message.message });
        this.client.emit("completed", {
          runId: this.runId,
          message: message.message,
        });
        break;
      case "RUN_ERROR":
        this._phase = "failed";
        this._error = message.message;
        this._trace.endedAt = Date.now();
        this.pushTrace("failed", "failed", { message: message.message });
        this.client.emit("failed", { runId: this.runId, message: message.message });
        break;
      case "PAYMENT_LINK_CONFIRMATION_REQUIRED":
        this._phase = "handoff";
        this.client.emit("payment_required", {
          runId: this.runId,
          proposal: message.proposal,
        });
        break;
      case "PAYMENT_LINK_READY":
        this.client.emit("payment_ready", {
          runId: this.runId,
          url: message.paymentLinkUrl,
          amountPaise: message.amountPaise,
          currency: message.currency,
        });
        break;
      case "PAYMENT_LINK_FAILED":
        this._phase = "failed";
        this._error = message.message;
        this.client.emit("failed", {
          runId: this.runId,
          message: message.message,
        });
        if (!message.recoverable) {
          this._trace.endedAt = Date.now();
          this.pushTrace("failed", "failed", { message: message.message });
        }
        break;
      default:
        break;
    }
  }

  private async drainQueue(): Promise<void> {
    if (this._processing || !this._actionQueue) {
      return;
    }
    this._processing = true;
    const message = this._actionQueue as Extract<
      ServerToClientMessage,
      { type: "NEXT_ACTION" }
    >;
    this._actionQueue = null;

    try {
      if (this._cancelled) {
        return;
      }

      this._phase = "acting";
      this.client.emit("action_started", {
        runId: this.runId,
        summary: message.actionSummary ?? "Executing",
      });
      this.pushTrace("action_started", "acting", {
        plan: {
          actionSummary: message.actionSummary,
          runtimePhase: message.runtimePhase,
        },
      });

      let lastStep = message.steps[message.steps.length - 1];
      let success = true;
      let error: string | undefined;
      let verified: boolean | undefined;

      for (const step of message.steps) {
        if (this._cancelled) {
          return;
        }

        if (
          step.action === "wait_for_user" ||
          step.action === "ready_for_payment_link"
        ) {
          await this.reportResult(step, true);
          return;
        }

        const result = await this.client.environment.executeStep(
          step,
          (summary) => {
            this.client.emit("action_started", {
              runId: this.runId,
              summary,
            });
          },
        );
        lastStep = step;
        verified = result.verified;
        if (!result.success || result.verified === false) {
          success = result.success;
          error = result.error;
          break;
        }
      }

      this._trace.metrics.actionsExecuted += 1;
      if (!success || verified === false) {
        this._trace.metrics.failedActions += 1;
      }

      await this.reportResult(lastStep, success, error, verified);

      this.client.emit("action_completed", {
        runId: this.runId,
        success,
        verified,
        error,
      });
      this.pushTrace("action_completed", success ? "verifying" : "recovering", {
        result: { success, verified, error },
      });
      this.client.emit("verification", {
        runId: this.runId,
        success,
        verified,
      });

      if (success) {
        this._phase = "planning";
        this.client.emit("planning", { runId: this.runId });
      } else {
        this._phase = "recovering";
        this._trace.metrics.recoveries += 1;
        this.client.emit("recovery", {
          runId: this.runId,
          message: error ?? "Action failed",
        });
      }
    } finally {
      this._processing = false;
      if (this._actionQueue) {
        void this.drainQueue();
      }
    }
  }

  private async reportResult(
    step: ActionStep,
    success: boolean,
    error?: string,
    verified?: boolean,
  ): Promise<void> {
    const pageContext = sanitizePageContextWire(
      (await this.client.environment.waitForStable?.()) ??
        (await this.client.environment.observeWire()),
    );
    this.client.transport.send({
      type: "ACTION_RESULT",
      runId: this.runId,
      step,
      success,
      error,
      verified,
      pageContext,
    });
  }

  private pushTrace(
    kind: TraceStep["kind"],
    phase: RunPhase,
    extra: Partial<TraceStep> = {},
  ): void {
    this._step += 1;
    this._trace.steps.push({
      step: this._step,
      kind,
      timestamp: Date.now(),
      phase,
      ...extra,
    });
    this._trace.status = phase;
  }
}

// ---------------------------------------------------------------------------
// RazorFlow client
// ---------------------------------------------------------------------------

export interface RazorFlowOptions {
  endpoint: string;
  apiKey?: string;
  transport?: Transport;
  environment: BrowserEnvironment;
  autoConnect?: boolean;
}

export interface RunOptions {
  task: string;
  url?: string;
  runId?: string;
}

export interface AgentConfigureOptions {
  useByok: boolean;
  provider?: string;
  apiKey?: string;
  model?: string;
  temperature?: number;
  maxAgentSteps?: number;
  shoppingSkillEnabled?: boolean;
}

export class RazorFlow {
  readonly transport: Transport;
  readonly environment: BrowserEnvironment;
  private readonly handlers = new Map<string, Set<EventHandler<keyof RazorFlowEventMap>>>();
  private activeRun: AgentRun | null = null;
  private unsubMessage: (() => void) | null = null;

  constructor(options: RazorFlowOptions) {
    this.environment = options.environment;
    this.transport =
      options.transport ??
      new WebSocketTransport(options.endpoint, options.apiKey);
    if (options.autoConnect !== false) {
      void this.transport.connect();
    }
    this.unsubMessage = this.transport.onMessage((msg) => {
      if (msg.type === "AGENT_SYNC") {
        this.emit("agent_sync", {
          runId: msg.runId,
          phase: msg.phase,
          actionSummary: msg.actionSummary,
          url: msg.url,
          step: msg.step,
          cursor: msg.cursor,
          highlight: msg.highlight,
        });
      }
      if (msg.type === "EXECUTOR_MODE") {
        this.emit("executor_mode", { runId: msg.runId, mode: msg.mode });
      }
      if (msg.type === "AGENT_CONFIG_STATUS") {
        this.emit("agent_config_status", {
          mode: msg.mode,
          useByok: msg.useByok,
          provider: msg.provider,
          model: msg.model,
          temperature: msg.temperature,
          maxAgentSteps: msg.maxAgentSteps,
          shoppingSkillEnabled: msg.shoppingSkillEnabled,
          message: msg.message,
        });
      }
      this.activeRun?.handleServerMessage(msg);
    });
    this.transport.onConnectionChange((connected) => {
      this.emit("connection_change", { connected });
    });
  }

  on<K extends keyof RazorFlowEventMap>(
    event: K,
    handler: EventHandler<K>,
  ): () => void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler as EventHandler<keyof RazorFlowEventMap>);
    this.handlers.set(event, set);
    return () => set.delete(handler as EventHandler<keyof RazorFlowEventMap>);
  }

  emit<K extends keyof RazorFlowEventMap>(
    event: K,
    payload: RazorFlowEventMap[K],
  ): void {
    for (const h of this.handlers.get(event) ?? []) {
      (h as EventHandler<K>)(payload);
    }
  }

  async connect(): Promise<void> {
    await this.transport.connect();
  }

  configureAgent(options: AgentConfigureOptions): void {
    if (!this.transport.isConnected()) {
      throw new RazorFlowError(
        "TRANSPORT_DISCONNECTED",
        "Connect before configuring the agent",
      );
    }
    this.transport.send({
      type: "CONFIGURE_AGENT",
      useByok: options.useByok,
      provider: options.provider,
      apiKey: options.apiKey,
      model: options.model,
      temperature: options.temperature,
      maxAgentSteps: options.maxAgentSteps,
      shoppingSkillEnabled: options.shoppingSkillEnabled,
    });
  }

  disconnect(): void {
    this.unsubMessage?.();
    this.transport.disconnect();
  }

  async run(options: RunOptions): Promise<AgentRun> {
    if (!this.transport.isConnected()) {
      await this.connect();
    }

    const runId = options.runId ?? crypto.randomUUID();
    const task = options.task.trim();
    const pageContext = sanitizePageContextWire(await this.environment.observeWire());

    const run = new AgentRun(runId, task, this);
    this.activeRun = run;

    this.transport.send({
      type: "START_RUN",
      runId,
      task,
      url: options.url ?? pageContext.url,
      pageContext,
    });

    this.emit("run_started", { runId, task });
    this.emit("planning", { runId });
    return run;
  }

  getActiveRun(): AgentRun | null {
    return this.activeRun;
  }
}

export { RazorFlow as default };

// Re-export protocol + browser types for SDK consumers
export type {
  ActionStep,
  BrowserObservation,
  ClientToServerMessage,
  PageContextWire,
  PaymentLinkProposal,
  RunPhase,
  RunTrace,
  ServerToClientMessage,
  TraceStep,
} from "@hardik21232323/razorflow-protocol";
export { sanitizePageContextWire, RazorFlowError } from "@hardik21232323/razorflow-protocol";
export type { BrowserEnvironment, StepResult } from "@hardik21232323/razorflow-browser";
export {
  buildBrowserObservation,
  observationToWire,
  DomBrowserEnvironment,
} from "@hardik21232323/razorflow-browser";
export type { RazorFlowErrorCode } from "@hardik21232323/razorflow-protocol";
