import type { AgentTimelineItem, AgentUiPhase } from "@/lib/agent/useAgentBridge";

export type AgentSessionStatus =
  | "idle"
  | "running"
  | "waiting"
  | "complete"
  | "error";

export interface AgentSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: AgentTimelineItem[];
  status: AgentSessionStatus;
  lastTask?: string;
}

const STORAGE_KEY = "razorflow-agent-sessions-v1";
const ACTIVE_KEY = "razorflow-agent-active-session-v1";

export function createSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function titleFromTask(task: string): string {
  const trimmed = task.trim();
  if (!trimmed) {
    return "New session";
  }
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}…` : trimmed;
}

export function statusFromPhase(phase: AgentUiPhase): AgentSessionStatus {
  switch (phase) {
    case "thinking":
    case "acting":
    case "observing":
    case "connecting":
      return "running";
    case "waiting_for_user":
    case "payment":
    case "payment_ready":
      return "waiting";
    case "complete":
      return "complete";
    case "error":
      return "error";
    default:
      return "idle";
  }
}

export function createEmptySession(title = "New session"): AgentSession {
  const now = Date.now();
  return {
    id: createSessionId(),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
    status: "idle",
  };
}

export function loadSessions(): AgentSession[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as AgentSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: AgentSession[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, 30)));
}

export function loadActiveSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveSessionId(id: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACTIVE_KEY, id);
}

export function formatSessionTime(at: number): string {
  const date = new Date(at);
  const now = new Date();
  const sameDay =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();

  if (sameDay) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}
