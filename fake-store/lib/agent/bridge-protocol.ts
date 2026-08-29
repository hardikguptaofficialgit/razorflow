/** WebSocket bridge protocol — re-exports SDK wire types plus demo-store helpers. */

import type {
  ActionStep,
  ClientToServerMessage,
  PageContextWire,
  PaymentLinkProposal,
  RuntimePhase,
  ServerToClientMessage,
} from "@hardik21232323/razorflow-protocol";

export type {
  ActionStep,
  PaymentLinkProposal,
  RuntimePhase,
  ClientToServerMessage,
  ServerToClientMessage,
};

export type BridgeConnectionStatus =
  | "connected"
  | "connecting"
  | "disconnected";

export type TargetRole = "search" | "input" | "button" | "link";

export type PageElementSummary = PageContextWire["elements"][number];
export type PageProductSummary = NonNullable<PageContextWire["products"]>[number];
export type PageCartLineSummary = NonNullable<PageContextWire["cartLines"]>[number];
export type PageContext = PageContextWire & {
  products: PageProductSummary[];
};

export type StartRunMessage = Extract<ClientToServerMessage, { type: "START_RUN" }>;
export type ActionResultMessage = Extract<
  ClientToServerMessage,
  { type: "ACTION_RESULT" }
>;
export type ResumeRunMessage = Extract<ClientToServerMessage, { type: "RESUME_RUN" }>;
export type CancelRunWsMessage = Extract<ClientToServerMessage, { type: "CANCEL_RUN" }>;
export type ConfirmPaymentLinkMessage = Extract<
  ClientToServerMessage,
  { type: "CONFIRM_PAYMENT_LINK" }
>;
export type DeclinePaymentLinkMessage = Extract<
  ClientToServerMessage,
  { type: "DECLINE_PAYMENT_LINK" }
>;

export type ClientToBackendMessage = ClientToServerMessage;

export type RunCompleteMessage = Extract<ServerToClientMessage, { type: "RUN_COMPLETE" }>;
export type RunWaitingForUserMessage = Extract<
  ServerToClientMessage,
  { type: "RUN_WAITING_FOR_USER" }
>;
export type RunNeedsClarificationMessage = Extract<
  ServerToClientMessage,
  { type: "RUN_NEEDS_CLARIFICATION" }
>;
export type RunErrorMessage = Extract<ServerToClientMessage, { type: "RUN_ERROR" }>;
export type PaymentLinkConfirmationMessage = Extract<
  ServerToClientMessage,
  { type: "PAYMENT_LINK_CONFIRMATION_REQUIRED" }
>;
export type PaymentLinkReadyMessage = Extract<
  ServerToClientMessage,
  { type: "PAYMENT_LINK_READY" }
>;
export type PaymentLinkFailedMessage = Extract<
  ServerToClientMessage,
  { type: "PAYMENT_LINK_FAILED" }
>;
export type AgentSyncCursor = NonNullable<
  Extract<ServerToClientMessage, { type: "AGENT_SYNC" }>["cursor"]
>;
export type AgentSyncHighlight = NonNullable<
  Extract<ServerToClientMessage, { type: "AGENT_SYNC" }>["highlight"]
>;
export type AgentSyncMessage = Extract<ServerToClientMessage, { type: "AGENT_SYNC" }>;
export type ExecutorModeMessage = Extract<
  ServerToClientMessage,
  { type: "EXECUTOR_MODE" }
>;
export type NextActionMessage = Extract<ServerToClientMessage, { type: "NEXT_ACTION" }>;

export type BackendToClientMessage = ServerToClientMessage;

export const DEFAULT_BRIDGE_WS_URL = "ws://127.0.0.1:8765/ws";

export function getBridgeWsUrl(): string {
  return (
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_AGENT_WS_URL?.trim()) ||
    DEFAULT_BRIDGE_WS_URL
  );
}

export function createRunId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `run-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
