import type { PaymentLinkProposal, PaymentLinkResult } from "./payment-link";

export type AgentState =
  | "idle"
  | "listening"
  | "thinking"
  | "acting"
  | "paused"
  | "waiting_for_user";

export type TargetRole = "search" | "input" | "button" | "link";

export interface CursorPosition {
  x: number;
  y: number;
}

export interface HighlightRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ElementMetadata {
  tag: string;
  text: string;
  placeholder: string;
  ariaLabel: string;
}

export interface DomTargetMatch {
  element: HTMLElement;
  metadata: ElementMetadata;
  rect: HighlightRect;
  center: CursorPosition;
}

export type ContentCommand =
  | { type: "SET_STATE"; state: AgentState }
  | { type: "MOVE_CURSOR"; x: number; y: number }
  | { type: "SHOW_HIGHLIGHT"; x: number; y: number; width: number; height: number }
  | { type: "CLEAR_HIGHLIGHT" }
  | { type: "PARK_CURSOR" }
  | { type: "TOGGLE_OVERLAY"; visible?: boolean }
  | { type: "HIGHLIGHT_ELEMENT"; role: TargetRole; elementIndex?: number; matchText?: string }
  | { type: "CLICK_ELEMENT"; role: TargetRole; elementIndex?: number; matchText?: string }
  | {
      type: "TYPE_IN_ELEMENT";
      role: TargetRole;
      text: string;
      elementIndex?: number;
      matchText?: string;
    }
  | { type: "RUN_DEMO_FLOW"; text?: string }
  | { type: "NAVIGATE_URL"; url: string }
  | { type: "ENTER_WAITING_FOR_USER"; message: string }
  | { type: "EXIT_WAITING_MODE" }
  | { type: "SHOW_PAYMENT_CONFIRMATION"; proposal: PaymentLinkProposal }
  | { type: "SHOW_PAYMENT_LINK_READY"; result: PaymentLinkResult }
  | { type: "HIDE_PAYMENT_HANDOFF" }
  | { type: "PING" }
  | { type: "SET_RUN_PHASE"; phase: "idle" | "running" | "planning" | "complete" | "error"; message?: string };

export interface OverlaySnapshot {
  visible: boolean;
  state: AgentState;
  cursor: CursorPosition;
}

export const AGENT_STATE_LABELS: Record<AgentState, string> = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  acting: "Acting",
  paused: "Paused",
  waiting_for_user: "Waiting for you",
};

export const OVERLAY_ROOT_ID = "razorflow-overlay-root";
