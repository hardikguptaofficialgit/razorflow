/** WebSocket bridge protocol — aligned with agent-backend/core/protocol.py */

export type BridgeConnectionStatus =
  | "connected"
  | "connecting"
  | "disconnected";

export type TargetRole = "search" | "input" | "button" | "link";

export interface PageElementSummary {
  index: number;
  role: TargetRole;
  tag: string;
  text: string;
  placeholder: string;
  ariaLabel: string;
  href?: string;
  value?: string;
  enabled?: boolean;
  bboxX?: number;
  bboxY?: number;
  bboxWidth?: number;
  bboxHeight?: number;
}

export interface PageProductSummary {
  title: string;
  priceText: string;
  ratingText: string;
  reviewCountText: string;
  availabilityText: string;
  elementIndex?: number;
  addToCartElementIndex?: number;
}

export interface PageCartLineSummary {
  title: string;
  quantity: number;
  removeElementIndex?: number;
}

export interface PageContext {
  title: string;
  url: string;
  elements: PageElementSummary[];
  products: PageProductSummary[];
  cartLines?: PageCartLineSummary[];
  screenshotDataUrl?: string;
}

export interface SetStateStep {
  action: "set_state";
  state: string;
}

export interface TypeInElementStep {
  action: "type_in_element";
  role: TargetRole;
  text: string;
  elementIndex?: number;
  matchText?: string;
}

export interface ClickElementStep {
  action: "click_element";
  role: TargetRole;
  elementIndex?: number;
  matchText?: string;
}

export interface HighlightElementStep {
  action: "highlight_element";
  role: TargetRole;
  elementIndex?: number;
  matchText?: string;
}

export interface NavigateUrlStep {
  action: "navigate_url";
  url: string;
}

export interface WaitForUserStep {
  action: "wait_for_user";
}

export interface ReadyForPaymentLinkStep {
  action: "ready_for_payment_link";
  title: string;
  description: string;
  amountPaise: number;
  currency: string;
}

export type ActionStep =
  | SetStateStep
  | TypeInElementStep
  | ClickElementStep
  | HighlightElementStep
  | NavigateUrlStep
  | WaitForUserStep
  | ReadyForPaymentLinkStep;

export interface StartRunMessage {
  type: "START_RUN";
  task: string;
  runId: string;
  url?: string;
  pageContext?: PageContext;
}

export interface ActionResultMessage {
  type: "ACTION_RESULT";
  runId: string;
  step: ActionStep;
  success: boolean;
  error?: string;
  verified?: boolean;
  pageContext?: PageContext;
}

export interface ResumeRunMessage {
  type: "RESUME_RUN";
  runId: string;
  pageContext?: PageContext;
}

export interface CancelRunWsMessage {
  type: "CANCEL_RUN";
  runId: string;
}

export interface ConfirmPaymentLinkMessage {
  type: "CONFIRM_PAYMENT_LINK";
  runId: string;
  confirmed: true;
}

export interface DeclinePaymentLinkMessage {
  type: "DECLINE_PAYMENT_LINK";
  runId: string;
}

export type ClientToBackendMessage =
  | StartRunMessage
  | ActionResultMessage
  | ResumeRunMessage
  | CancelRunWsMessage
  | ConfirmPaymentLinkMessage
  | DeclinePaymentLinkMessage;

export interface RunCompleteMessage {
  type: "RUN_COMPLETE";
  runId: string;
  message?: string;
}

export interface RunWaitingForUserMessage {
  type: "RUN_WAITING_FOR_USER";
  runId: string;
  message?: string;
}

export interface RunNeedsClarificationMessage {
  type: "RUN_NEEDS_CLARIFICATION";
  runId: string;
  message: string;
}

export interface RunErrorMessage {
  type: "RUN_ERROR";
  runId: string;
  message: string;
}

export interface PaymentLinkProposal {
  title: string;
  description: string;
  amountPaise: number;
  currency: string;
}

export interface PaymentLinkConfirmationMessage {
  type: "PAYMENT_LINK_CONFIRMATION_REQUIRED";
  runId: string;
  proposal: PaymentLinkProposal;
  message?: string;
}

export interface PaymentLinkReadyMessage {
  type: "PAYMENT_LINK_READY";
  runId: string;
  paymentLinkUrl: string;
  amountPaise: number;
  currency: string;
  description: string;
  referenceId: string;
  message?: string;
}

export interface PaymentLinkFailedMessage {
  type: "PAYMENT_LINK_FAILED";
  runId: string;
  message: string;
  recoverable?: boolean;
}

export interface AgentSyncCursor {
  x: number;
  y: number;
}

export interface AgentSyncHighlight {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AgentSyncMessage {
  type: "AGENT_SYNC";
  runId: string;
  phase: "thinking" | "acting" | "observing";
  url: string;
  title: string;
  step: number;
  actionSummary: string;
  cursor?: AgentSyncCursor;
  highlight?: AgentSyncHighlight;
}

export interface ExecutorModeMessage {
  type: "EXECUTOR_MODE";
  runId: string;
  mode: "browser_use" | "extension_dom";
}

export type RuntimePhase =
  | "planning"
  | "observing"
  | "acting"
  | "waiting"
  | "verifying"
  | "recovering"
  | "handoff"
  | "done";

export interface NextActionMessage {
  type: "NEXT_ACTION";
  runId: string;
  steps: ActionStep[];
  turn: number;
  actionSummary?: string;
  screenshotDataUrl?: string;
  runtimePhase?: RuntimePhase;
}

export type BackendToClientMessage =
  | RunCompleteMessage
  | RunWaitingForUserMessage
  | RunNeedsClarificationMessage
  | RunErrorMessage
  | PaymentLinkConfirmationMessage
  | PaymentLinkReadyMessage
  | PaymentLinkFailedMessage
  | AgentSyncMessage
  | ExecutorModeMessage
  | NextActionMessage;

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
