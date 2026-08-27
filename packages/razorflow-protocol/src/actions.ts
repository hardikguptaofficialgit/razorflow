/** Action safety classification — core runtime uses for policy gates. */

export type ActionSafety = "read" | "write" | "high_risk";

export type AgentActionType =
  | "navigate"
  | "click"
  | "type"
  | "select"
  | "scroll"
  | "wait"
  | "search"
  | "extract"
  | "go_back"
  | "open_tab"
  | "close_tab"
  | "finish"
  | "handoff";

export const ACTION_SAFETY: Record<AgentActionType, ActionSafety> = {
  navigate: "write",
  click: "write",
  type: "write",
  select: "write",
  scroll: "read",
  wait: "read",
  search: "read",
  extract: "read",
  go_back: "write",
  open_tab: "write",
  close_tab: "write",
  finish: "read",
  handoff: "read",
};

/** High-risk wire actions require policy confirmation on the server. */
export const HIGH_RISK_WIRE_ACTIONS = new Set(["ready_for_payment_link"]);
