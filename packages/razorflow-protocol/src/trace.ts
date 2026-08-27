/** First-class run trace for SDK consumers. */

export type RunPhase =
  | "idle"
  | "observing"
  | "planning"
  | "acting"
  | "verifying"
  | "recovering"
  | "handoff"
  | "completed"
  | "failed"
  | "cancelled";

export type TraceEventKind =
  | "run_started"
  | "observing"
  | "planning"
  | "action_started"
  | "action_completed"
  | "verification"
  | "recovery"
  | "handoff"
  | "completed"
  | "failed";

export interface TraceStep {
  step: number;
  kind: TraceEventKind;
  timestamp: number;
  phase: RunPhase;
  durationMs?: number;
  observation?: { url: string; title: string; elementCount: number };
  plan?: { actionSummary?: string; runtimePhase?: string };
  action?: { type: string; summary?: string; target?: string };
  result?: { success: boolean; verified?: boolean; error?: string };
  llm?: { provider?: string; model?: string; latencyMs?: number };
  recovery?: { reason: string };
  message?: string;
}

export interface RunTrace {
  runId: string;
  task: string;
  startedAt: number;
  endedAt?: number;
  status: RunPhase;
  steps: TraceStep[];
  metrics: {
    llmCalls: number;
    actionsExecuted: number;
    recoveries: number;
    failedActions: number;
    totalDurationMs: number;
  };
}
