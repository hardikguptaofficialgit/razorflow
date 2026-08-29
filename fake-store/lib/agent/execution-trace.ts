/**
 * Runtime execution trace for validation — enabled via window.__RF_ENABLE_EXECUTION_TRACE__.
 * Not used in production UI; consumed by real-browser test harnesses.
 */

export interface ExecutionTraceEntry {
  at: number;
  kind:
    | "action_start"
    | "target_resolved"
    | "cursor_position"
    | "action_result"
    | "page_state";
  step?: Record<string, unknown>;
  target?: {
    tag: string;
    text: string;
    rect: { x: number; y: number; width: number; height: number };
    productId?: string;
  };
  cursor?: { x: number; y: number };
  result?: { success: boolean; verified?: boolean; error?: string };
  page?: { url: string; signature: string; cartCount: number };
}

declare global {
  interface Window {
    __RF_ENABLE_EXECUTION_TRACE__?: boolean;
    __RF_EXECUTION_TRACE__?: ExecutionTraceEntry[];
    __RF_WS_TRACE__?: Array<{ direction: "in" | "out"; type: string; at: number }>;
  }
}

export function executionTraceEnabled(): boolean {
  return (
    typeof window !== "undefined" && window.__RF_ENABLE_EXECUTION_TRACE__ === true
  );
}

export function pushExecutionTrace(entry: Omit<ExecutionTraceEntry, "at">): void {
  if (!executionTraceEnabled()) {
    return;
  }
  if (!window.__RF_EXECUTION_TRACE__) {
    window.__RF_EXECUTION_TRACE__ = [];
  }
  window.__RF_EXECUTION_TRACE__.push({ ...entry, at: Date.now() });
}

export function clearExecutionTrace(): void {
  if (typeof window !== "undefined") {
    window.__RF_EXECUTION_TRACE__ = [];
    window.__RF_WS_TRACE__ = [];
  }
}

export function installWebSocketTrace(): void {
  if (typeof window === "undefined" || !executionTraceEnabled()) {
    return;
  }
  if ((window as Window & { __RF_WS_PATCHED__?: boolean }).__RF_WS_PATCHED__) {
    return;
  }
  (window as Window & { __RF_WS_PATCHED__?: boolean }).__RF_WS_PATCHED__ = true;
  const Original = window.WebSocket;
  window.WebSocket = function WebSocketPatched(
    this: WebSocket,
    url: string | URL,
    protocols?: string | string[],
  ) {
    const ws =
      protocols !== undefined
        ? new Original(url, protocols)
        : new Original(url);
    const record = (direction: "in" | "out", raw: string) => {
      try {
        const parsed = JSON.parse(raw) as { type?: string };
        if (!window.__RF_WS_TRACE__) {
          window.__RF_WS_TRACE__ = [];
        }
        window.__RF_WS_TRACE__.push({
          direction,
          type: parsed.type ?? "unknown",
          at: Date.now(),
        });
      } catch {
        /* ignore */
      }
    };
    ws.addEventListener("message", (event) => record("in", String(event.data)));
    const send = ws.send.bind(ws);
    ws.send = (data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
      if (typeof data === "string") {
        record("out", data);
      }
      send(data);
    };
    return ws;
  } as unknown as typeof WebSocket;
  window.WebSocket.prototype = Original.prototype;
}
