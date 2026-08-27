import type { ActionStep } from "../shared/bridge-protocol";
import type {
  PreservedRunContext,
  RunTimelineSnapshot,
  TimelineEvent,
  TimelineEventKind,
} from "../shared/run-timeline";

const MAX_EVENTS = 40;

function createEvent(
  runId: string,
  kind: TimelineEventKind,
  label: string,
): TimelineEvent {
  return {
    id: crypto.randomUUID(),
    kind,
    label,
    timestamp: Date.now(),
    runId,
  };
}

function describeAttempt(step: ActionStep): string | null {
  switch (step.action) {
    case "set_state":
      if (step.state === "thinking") {
        return "Thinking";
      }
      if (step.state === "acting") {
        return "Acting";
      }
      return null;
    case "type_in_element":
      return `Typing in ${step.role} field…`;
    case "click_element":
      return `Clicking ${step.role}…`;
    case "highlight_element":
      return `Highlighting ${step.role}…`;
    case "wait_for_user":
      return null;
    case "ready_for_payment_link":
      return `Ready for payment: ${step.title}`;
    default:
      return null;
  }
}

function describeSuccess(step: ActionStep): string | null {
  switch (step.action) {
    case "type_in_element":
      return `Typed in ${step.role} field`;
    case "click_element":
      return `Clicked ${step.role}`;
    case "highlight_element":
      return `Highlighted ${step.role}`;
    case "ready_for_payment_link":
      return `Ready for payment: ${step.title}`;
    default:
      return null;
  }
}

function describeFailure(step: ActionStep, error?: string): string {
  const base =
    step.action === "type_in_element"
      ? `Failed typing in ${step.role}`
      : step.action === "click_element"
        ? `Failed clicking ${step.role}`
        : step.action === "highlight_element"
          ? `Failed highlighting ${step.role}`
          : "Failed";
  if (error?.trim()) {
    return `${base}: ${error.trim()}`;
  }
  return base;
}

export class RunSessionStore {
  private context: PreservedRunContext = {
    runId: null,
    task: null,
    waitingMessage: null,
    status: "idle",
  };

  private events: TimelineEvent[] = [];
  private lastAgentSyncLabel: string | null = null;

  getSnapshot(): RunTimelineSnapshot {
    return {
      context: { ...this.context },
      events: [...this.events],
    };
  }

  startRun(runId: string, task: string): void {
    this.context = {
      runId,
      task,
      waitingMessage: null,
      status: "active",
    };
    this.events = [];
    this.lastAgentSyncLabel = null;
    this.push(runId, "run_started", `Task started — ${task}`);
  }

  /** Log intent before execution — never claim success here. */
  logStepAttempts(runId: string, steps: ActionStep[]): void {
    for (const step of steps) {
      if (step.action === "set_state" && step.state === "thinking") {
        this.push(runId, "thinking", "Thinking");
        continue;
      }
      const label = describeAttempt(step);
      if (!label) {
        continue;
      }
      this.push(runId, "thinking", label);
    }
  }

  logStepResult(
    runId: string,
    step: ActionStep,
    success: boolean,
    error?: string,
  ): void {
    if (step.action === "set_state" || step.action === "wait_for_user") {
      return;
    }

    if (success) {
      const label = describeSuccess(step);
      if (label) {
        this.push(runId, "acted", label);
      }
      return;
    }

    this.push(runId, "action_failed", describeFailure(step, error));
  }

  setWaiting(runId: string, message: string): void {
    this.context = {
      ...this.context,
      runId,
      waitingMessage: message,
      status: "waiting_for_user",
    };
    this.push(runId, "waiting_for_user", message);
  }

  setResumed(runId: string): void {
    this.context = {
      ...this.context,
      runId,
      waitingMessage: null,
      status: "active",
    };
    this.push(runId, "resumed", "Resumed after your manual step");
  }

  setCompleted(runId: string): void {
    this.push(runId, "completed", "Run completed");
    this.resetIfMatches(runId);
  }

  setCancelled(runId: string): void {
    this.push(runId, "cancelled", "Run cancelled");
    this.resetIfMatches(runId);
  }

  setError(runId: string, message: string): void {
    this.push(runId, "error", message);
    this.resetIfMatches(runId);
  }

  logPaymentConfirmation(runId: string, label: string): void {
    this.push(runId, "payment_confirmation", label);
  }

  logPolicyCheck(runId: string, label: string): void {
    this.push(runId, "policy_check", label);
  }

  logPolicyApproved(runId: string, label: string): void {
    this.push(runId, "policy_approved", label);
  }

  logPolicyBlocked(runId: string, label: string): void {
    this.push(runId, "policy_blocked", label);
  }

  logMcpPaymentLink(runId: string, label: string): void {
    this.push(runId, "mcp_payment_link", label);
  }

  logPaymentLinkReady(runId: string, label: string): void {
    this.push(runId, "payment_link_ready", label);
  }

  logPaymentLinkFailed(runId: string, label: string): void {
    this.push(runId, "payment_link_failed", label);
  }

  logAgentSync(runId: string, label: string): void {
    const trimmed = label.trim();
    if (!trimmed || trimmed === this.lastAgentSyncLabel) {
      return;
    }
    this.lastAgentSyncLabel = trimmed;
    this.push(runId, "acted", trimmed);
  }

  getWaitingRunId(): string | null {
    return this.context.status === "waiting_for_user"
      ? this.context.runId
      : null;
  }

  private push(runId: string, kind: TimelineEventKind, label: string): void {
    this.events.push(createEvent(runId, kind, label));
    if (this.events.length > MAX_EVENTS) {
      this.events = this.events.slice(-MAX_EVENTS);
    }

    void chrome.runtime.sendMessage({
      type: "RUN_TIMELINE_UPDATE",
      snapshot: this.getSnapshot(),
    });
  }

  private resetIfMatches(runId: string): void {
    if (this.context.runId !== runId) {
      return;
    }

    this.context = {
      runId: null,
      task: null,
      waitingMessage: null,
      status: "idle",
    };
  }
}

export const runSessionStore = new RunSessionStore();
