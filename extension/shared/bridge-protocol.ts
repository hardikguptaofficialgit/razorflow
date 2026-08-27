import type { PaymentAuditSnapshot } from "./audit";
import type { PaymentLinkProposal, PaymentLinkResult } from "./payment-link";
import type { PageContext } from "./page-context";
import type { AgentState, TargetRole } from "./types";
import type { RunTimelineSnapshot } from "./run-timeline";

export type BridgeConnectionStatus =
  | "connected"
  | "connecting"
  | "disconnected";

export type ActionStep =
  | { action: "set_state"; state: AgentState }
  | {
      action: "type_in_element";
      role: TargetRole;
      text: string;
      elementIndex?: number;
      matchText?: string;
    }
  | {
      action: "click_element";
      role: TargetRole;
      elementIndex?: number;
      matchText?: string;
    }
  | {
      action: "highlight_element";
      role: TargetRole;
      elementIndex?: number;
      matchText?: string;
    }
  | { action: "navigate_url"; url: string }
  | { action: "wait_for_user" }
  | {
      action: "ready_for_payment_link";
      title: string;
      description: string;
      amountPaise: number;
      currency: string;
    };

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

export type ExtensionToBackendMessage =
  | StartRunMessage
  | ActionResultMessage
  | ResumeRunMessage
  | CancelRunWsMessage
  | ConfirmPaymentLinkMessage
  | DeclinePaymentLinkMessage;

export interface NextActionMessage {
  type: "NEXT_ACTION";
  runId: string;
  steps: ActionStep[];
  turn: number;
}

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

export interface RunErrorMessage {
  type: "RUN_ERROR";
  runId: string;
  message: string;
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

export type BackendToExtensionMessage =
  | NextActionMessage
  | RunCompleteMessage
  | RunWaitingForUserMessage
  | RunErrorMessage
  | PaymentLinkConfirmationMessage
  | PaymentLinkReadyMessage
  | PaymentLinkFailedMessage
  | AgentSyncMessage
  | ExecutorModeMessage;

export type PopupToBackgroundMessage =
  | { type: "START_RUN"; task: string; runId: string }
  | { type: "RESUME_RUN"; runId: string }
  | { type: "GET_BRIDGE_STATUS" }
  | { type: "GET_RUN_TIMELINE" }
  | { type: "CANCEL_RUN" }
  | { type: "CONFIRM_PAYMENT_LINK"; runId: string }
  | { type: "DECLINE_PAYMENT_LINK"; runId: string }
  | { type: "GET_PAYMENT_AUDIT"; runId: string };

export interface BridgeStatusResponse {
  type: "BRIDGE_STATUS";
  status: BridgeConnectionStatus;
}

export interface TaskSubmitResponse {
  type: "TASK_SUBMITTED";
  task: string;
  runId: string;
}

export interface TaskErrorResponse {
  type: "TASK_ERROR";
  message: string;
}

export interface CancelRunResponse {
  type: "RUN_CANCELLED";
}

export interface ResumeRunResponse {
  type: "RUN_RESUMED";
  runId: string;
}

export interface RunTimelineResponse {
  type: "RUN_TIMELINE";
  snapshot: RunTimelineSnapshot;
}

export interface PaymentAuditResponse {
  type: "PAYMENT_AUDIT";
  snapshot: PaymentAuditSnapshot;
}

export type BackgroundToPopupMessage =
  | BridgeStatusResponse
  | TaskSubmitResponse
  | TaskErrorResponse
  | CancelRunResponse
  | ResumeRunResponse
  | RunTimelineResponse
  | PaymentAuditResponse;

export const BRIDGE_WS_URL = "ws://127.0.0.1:8765/ws";
