import type { AgentSessionStatus } from "@/lib/agent/agent-sessions";
import type { AgentTimelineItem, AgentUiPhase } from "@/lib/agent/useAgentBridge";

export const AGENT_SUGGESTIONS = [
  "Cheapest shampoo under ₹500",
  "Wireless earbuds best value",
  "Snacks under ₹200",
];

export function phaseLabel(phase: AgentUiPhase, connected: boolean): string {
  if (!connected) return "Offline";
  switch (phase) {
    case "connecting":
      return "Connecting";
    case "thinking":
    case "observing":
      return "Planning";
    case "acting":
      return "Acting";
    case "waiting_for_user":
      return "Handoff";
    case "payment":
      return "Payment";
    case "payment_ready":
      return "Payment ready";
    case "complete":
      return "Complete";
    case "error":
      return "Error";
    default:
      return "Ready";
  }
}

export function isBusy(phase: AgentUiPhase): boolean {
  return (
    phase === "thinking" ||
    phase === "acting" ||
    phase === "observing" ||
    phase === "connecting"
  );
}

export function timelineKindLabel(kind: AgentTimelineItem["kind"]): string {
  switch (kind) {
    case "info":
      return "Task";
    case "sync":
      return "Action";
    case "success":
      return "Done";
    case "error":
      return "Error";
    case "wait":
      return "Handoff";
    default:
      return "Update";
  }
}

export function sessionStatusLabel(status: AgentSessionStatus): string {
  switch (status) {
    case "running":
      return "Running";
    case "waiting":
      return "Waiting";
    case "complete":
      return "Done";
    case "error":
      return "Error";
    default:
      return "";
  }
}

export function formatTimelineTime(at: number): string {
  return new Date(at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
