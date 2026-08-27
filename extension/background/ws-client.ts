import {
  BRIDGE_WS_URL,
  type BridgeConnectionStatus,
  type ExtensionToBackendMessage,
} from "../shared/bridge-protocol";
import { parseBackendMessage } from "../shared/plan";
import type { PageContext } from "../shared/page-context";
import { runLoopController } from "./run-loop";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

type StatusListener = (status: BridgeConnectionStatus) => void;

export class BridgeWebSocketClient {
  private socket: WebSocket | null = null;
  private status: BridgeConnectionStatus = "disconnected";
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private readonly listeners = new Set<StatusListener>();

  constructor() {
    runLoopController.bindSender((message) => this.send(message));
  }

  connect(): void {
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.clearReconnectTimer();
    this.setStatus("connecting");

    const socket = new WebSocket(BRIDGE_WS_URL);
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus("connected");
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const payload: unknown = JSON.parse(event.data);
        const message = parseBackendMessage(payload);
        if (message) {
          runLoopController.handleBackendMessage(message);
        }
      } catch {
        // Ignore malformed backend payloads.
      }
    };

    socket.onerror = () => {
      socket.close();
    };

    socket.onclose = () => {
      this.socket = null;
      this.setStatus("disconnected");
      this.scheduleReconnect();
    };
  }

  subscribe(listener: StatusListener): () => void {
    this.listeners.add(listener);
    listener(this.status);

    return () => {
      this.listeners.delete(listener);
    };
  }

  getStatus(): BridgeConnectionStatus {
    return this.status;
  }

  send(message: ExtensionToBackendMessage): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.connect();
      throw new Error("Backend is not connected. Retrying connection...");
    }

    this.socket.send(JSON.stringify(message));
  }

  async startRun(
    task: string,
    runId: string,
    url?: string,
    pageContext?: PageContext,
  ): Promise<void> {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.connect();
      throw new Error("Backend is not connected. Retrying connection...");
    }

    await runLoopController.startRun(task, runId, url, pageContext);
  }

  async resumeRun(runId: string, pageContext?: PageContext): Promise<void> {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.connect();
      throw new Error("Backend is not connected. Retrying connection...");
    }

    await runLoopController.resumeRun(runId, pageContext);
  }

  private setStatus(status: BridgeConnectionStatus): void {
    this.status = status;
    this.listeners.forEach((listener) => listener(status));
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return;
    }

    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_MS,
    );

    this.reconnectAttempt += 1;
    this.reconnectTimer = self.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      self.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
