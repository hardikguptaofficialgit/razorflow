export type TimelineEventKind =
  | "run_started"
  | "thinking"
  | "acted"
  | "action_failed"
  | "waiting_for_user"
  | "resumed"
  | "completed"
  | "cancelled"
  | "error"
  | "payment_confirmation"
  | "policy_check"
  | "policy_approved"
  | "policy_blocked"
  | "mcp_payment_link"
  | "payment_link_ready"
  | "payment_link_failed";

export interface TimelineEvent {
  id: string;
  kind: TimelineEventKind;
  label: string;
  timestamp: number;
  runId: string;
}

export interface PreservedRunContext {
  runId: string | null;
  task: string | null;
  waitingMessage: string | null;
  status: "idle" | "active" | "waiting_for_user";
}

export interface RunTimelineSnapshot {
  context: PreservedRunContext;
  events: TimelineEvent[];
}

export interface RunTimelineUpdateMessage {
  type: "RUN_TIMELINE_UPDATE";
  snapshot: RunTimelineSnapshot;
}

export interface OverlayResumeMessage {
  type: "OVERLAY_RESUME_RUN";
}

export interface OverlayCancelMessage {
  type: "OVERLAY_CANCEL_RUN";
}

export const DEFAULT_WAITING_MESSAGE =
  "Please complete the required step, then resume when ready.";
