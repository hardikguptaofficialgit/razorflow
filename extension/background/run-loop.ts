import type {
  BackendToExtensionMessage,
  ConfirmPaymentLinkMessage,
  DeclinePaymentLinkMessage,
} from "../shared/bridge-protocol";
import { DEFAULT_WAITING_MESSAGE } from "../shared/run-timeline";
import type { PageContext } from "../shared/page-context";
import { requestPageContextFromActiveTab, sendToActiveTab } from "../shared/messaging";
import { runSessionStore } from "./run-session";
import { executeActionStep } from "./step-executor";

type SendWsMessage = (message: ExtensionOutboundMessage) => void;

type ExtensionOutboundMessage =
  | import("../shared/bridge-protocol").StartRunMessage
  | import("../shared/bridge-protocol").ActionResultMessage
  | import("../shared/bridge-protocol").ResumeRunMessage
  | import("../shared/bridge-protocol").CancelRunWsMessage
  | ConfirmPaymentLinkMessage
  | DeclinePaymentLinkMessage;

export class RunLoopController {
  private activeRunId: string | null = null;
  private waitingRunId: string | null = null;
  private cancelled = false;
  private sendMessage: SendWsMessage | null = null;
  private pendingPaymentRunId: string | null = null;
  private pendingPaymentLinkUrl: string | null = null;
  private executorMode: "browser_use" | "extension_dom" = "extension_dom";
  private agentSyncWatchdog: ReturnType<typeof setTimeout> | null = null;
  private static readonly AGENT_SYNC_STALL_MS = 200_000;

  bindSender(sender: SendWsMessage): void {
    this.sendMessage = sender;
  }

  getWaitingRunId(): string | null {
    return this.waitingRunId ?? runSessionStore.getWaitingRunId();
  }

  getPendingPaymentRunId(): string | null {
    return this.pendingPaymentRunId;
  }

  getPendingPaymentLinkUrl(): string | null {
    return this.pendingPaymentLinkUrl;
  }

  confirmPaymentLink(runId: string): void {
    runSessionStore.logPolicyCheck(runId, "Policy check started");
    this.sendMessage?.({
      type: "CONFIRM_PAYMENT_LINK",
      runId,
      confirmed: true,
    });
  }

  declinePaymentLink(runId: string): void {
    this.sendMessage?.({
      type: "DECLINE_PAYMENT_LINK",
      runId,
    });
    this.pendingPaymentRunId = null;
    void sendToActiveTab({ type: "HIDE_PAYMENT_HANDOFF" });
  }

  async startRun(
    task: string,
    runId: string,
    url?: string,
    pageContext?: PageContext,
  ): Promise<void> {
    this.cancelled = false;
    this.activeRunId = runId;
    this.waitingRunId = null;
    this.pendingPaymentRunId = null;
    this.executorMode = "extension_dom";

    runSessionStore.startRun(runId, task);
    void sendToActiveTab({
      type: "SET_RUN_PHASE",
      phase: "planning",
      message: "Planning next step…",
    });
    void sendToActiveTab({ type: "EXIT_WAITING_MODE" });
    void sendToActiveTab({ type: "HIDE_PAYMENT_HANDOFF" });
    void sendToActiveTab({ type: "SET_STATE", state: "thinking" });

    this.sendMessage?.({
      type: "START_RUN",
      task,
      runId,
      url,
      pageContext,
    });
  }

  async resumeRun(runId: string, pageContext?: PageContext): Promise<void> {
    this.cancelled = false;
    this.activeRunId = runId;
    this.waitingRunId = null;
    this.clearAgentSyncWatchdog();

    runSessionStore.setResumed(runId);
    void sendToActiveTab({ type: "EXIT_WAITING_MODE" });
    void sendToActiveTab({ type: "HIDE_PAYMENT_HANDOFF" });
    void sendToActiveTab({ type: "PARK_CURSOR" });
    void sendToActiveTab({ type: "SET_STATE", state: "thinking" });
    void sendToActiveTab({
      type: "SET_RUN_PHASE",
      phase: "running",
      message: "Resuming…",
    });

    this.sendMessage?.({
      type: "RESUME_RUN",
      runId,
      pageContext,
    });
  }

  cancelRun(): void {
    this.cancelled = true;
    this.clearAgentSyncWatchdog();
    const runId = this.activeRunId ?? this.waitingRunId;

    if (runId) {
      this.sendMessage?.({
        type: "CANCEL_RUN",
        runId,
      });
      runSessionStore.setCancelled(runId);
    }

    this.activeRunId = null;
    this.waitingRunId = null;
    this.pendingPaymentRunId = null;
    void sendToActiveTab({ type: "EXIT_WAITING_MODE" });
    void sendToActiveTab({ type: "HIDE_PAYMENT_HANDOFF" });
    void sendToActiveTab({ type: "PARK_CURSOR" });
    void sendToActiveTab({ type: "SET_STATE", state: "idle" });
  }

  handleBackendMessage(message: BackendToExtensionMessage): void {
    switch (message.type) {
      case "EXECUTOR_MODE":
        if (
          message.runId === this.activeRunId ||
          message.runId === this.waitingRunId ||
          !this.activeRunId
        ) {
          if (!this.activeRunId) {
            this.activeRunId = message.runId;
          }
          this.executorMode = message.mode;
        }
        break;
      case "AGENT_SYNC":
        this.executorMode = "browser_use";
        void this.handleAgentSync(message);
        break;
      case "NEXT_ACTION":
        if (this.executorMode === "browser_use") {
          return;
        }
        void this.handleNextAction(message);
        break;
      case "RUN_COMPLETE":
        this.clearAgentSyncWatchdog();
        runSessionStore.setCompleted(message.runId);
        void sendToActiveTab({
          type: "SET_RUN_PHASE",
          phase: "complete",
          message: "Task completed",
        });
        this.finishRun(message.runId);
        break;
      case "RUN_WAITING_FOR_USER": {
        this.clearAgentSyncWatchdog();
        const waitingMessage =
          message.message?.trim() || DEFAULT_WAITING_MESSAGE;

        this.waitingRunId = message.runId;
        this.activeRunId = null;

        runSessionStore.setWaiting(message.runId, waitingMessage);
        void sendToActiveTab({ type: "PARK_CURSOR" });
        void sendToActiveTab({
          type: "ENTER_WAITING_FOR_USER",
          message: waitingMessage,
        });

        void chrome.runtime.sendMessage({
          type: "RUN_WAITING_FOR_USER",
          runId: message.runId,
          message: waitingMessage,
        });
        break;
      }
      case "PAYMENT_LINK_CONFIRMATION_REQUIRED": {
        this.pendingPaymentRunId = message.runId;
        this.waitingRunId = message.runId;
        this.activeRunId = null;

        runSessionStore.setWaiting(
          message.runId,
          message.message ?? "Confirm payment link creation.",
        );
        runSessionStore.logPaymentConfirmation(
          message.runId,
          "Payment confirmation requested — review amount and details.",
        );
        void sendToActiveTab({
          type: "SHOW_PAYMENT_CONFIRMATION",
          proposal: message.proposal,
        });

        void chrome.runtime.sendMessage({
          type: "PAYMENT_LINK_CONFIRMATION_REQUIRED",
          runId: message.runId,
          proposal: message.proposal,
        });
        break;
      }
      case "PAYMENT_LINK_READY": {
        this.pendingPaymentRunId = message.runId;
        this.pendingPaymentLinkUrl = message.paymentLinkUrl;
        this.waitingRunId = message.runId;
        this.activeRunId = null;

        runSessionStore.logPolicyApproved(
          message.runId,
          "Policy approved payment link.",
        );
        runSessionStore.logMcpPaymentLink(
          message.runId,
          "MCP create_payment_link succeeded.",
        );
        runSessionStore.logPaymentLinkReady(
          message.runId,
          `Payment link ready (${message.currency} ${message.amountPaise / 100}).`,
        );
        runSessionStore.setWaiting(
          message.runId,
          message.message ?? "Payment link ready.",
        );

        void sendToActiveTab({
          type: "SHOW_PAYMENT_LINK_READY",
          result: {
            paymentLinkUrl: message.paymentLinkUrl,
            amountPaise: message.amountPaise,
            currency: message.currency,
            description: message.description,
            referenceId: message.referenceId,
          },
        });

        void chrome.runtime.sendMessage({
          type: "PAYMENT_LINK_READY",
          runId: message.runId,
          paymentLinkUrl: message.paymentLinkUrl,
          amountPaise: message.amountPaise,
          currency: message.currency,
          description: message.description,
          referenceId: message.referenceId,
        });
        break;
      }
      case "PAYMENT_LINK_FAILED": {
        if (message.message.toLowerCase().includes("policy")) {
          runSessionStore.logPolicyBlocked(message.runId, message.message);
        } else {
          runSessionStore.logPaymentLinkFailed(message.runId, message.message);
        }
        if (message.recoverable) {
          this.waitingRunId = message.runId;
          this.activeRunId = null;
          runSessionStore.setWaiting(
            message.runId,
            message.message,
          );
          void sendToActiveTab({
            type: "ENTER_WAITING_FOR_USER",
            message: message.message,
          });
        }

        void chrome.runtime.sendMessage({
          type: "PAYMENT_LINK_FAILED",
          runId: message.runId,
          message: message.message,
        });
        break;
      }
      case "RUN_ERROR":
        this.clearAgentSyncWatchdog();
        runSessionStore.setError(
          message.runId,
          message.message ?? "Run failed",
        );
        void sendToActiveTab({ type: "PARK_CURSOR" });
        void sendToActiveTab({
          type: "SET_RUN_PHASE",
          phase: "error",
          message: message.message ?? "Run failed",
        });
        this.finishRun(message.runId);
        break;
    }
  }

  private async handleAgentSync(
    message: Extract<BackendToExtensionMessage, { type: "AGENT_SYNC" }>,
  ): Promise<void> {
    if (this.cancelled) {
      return;
    }

    if (this.activeRunId !== message.runId && this.waitingRunId !== message.runId) {
      this.activeRunId = message.runId;
    }

    const agentState =
      message.phase === "acting"
        ? "acting"
        : message.phase === "thinking"
          ? "thinking"
          : "acting";

    void sendToActiveTab({ type: "SET_STATE", state: agentState });
    void sendToActiveTab({
      type: "SET_RUN_PHASE",
      phase: "running",
      message: message.actionSummary || "Working…",
    });

    if (message.cursor) {
      void sendToActiveTab({
        type: "MOVE_CURSOR",
        x: message.cursor.x,
        y: message.cursor.y,
      });
    } else if (message.phase === "thinking") {
      // Don't leave the fake cursor frozen on the last click target (e.g. logo).
      void sendToActiveTab({ type: "PARK_CURSOR" });
    }

    if (message.highlight) {
      void sendToActiveTab({
        type: "SHOW_HIGHLIGHT",
        x: message.highlight.x,
        y: message.highlight.y,
        width: message.highlight.width,
        height: message.highlight.height,
      });
    } else if (message.phase === "thinking") {
      void sendToActiveTab({ type: "CLEAR_HIGHLIGHT" });
    }

    runSessionStore.logAgentSync(
      message.runId,
      message.actionSummary || message.phase,
    );
    this.armAgentSyncWatchdog(message.runId);
  }

  private async handleNextAction(message: NextActionMessage): Promise<void> {
    if (this.cancelled || this.activeRunId !== message.runId) {
      return;
    }

    runSessionStore.logStepAttempts(message.runId, message.steps);

    for (const step of message.steps) {
      if (this.cancelled || this.activeRunId !== message.runId) {
        return;
      }

      void sendToActiveTab({
        type: "SET_RUN_PHASE",
        phase: "running",
        message: "Executing…",
      });

      let result = await executeActionStep(step);

      if (result.code === "CONNECTION_LOST") {
        void sendToActiveTab({
          type: "SET_RUN_PHASE",
          phase: "error",
          message: "Browser connection lost. Reconnecting…",
        });

        await new Promise((resolve) => setTimeout(resolve, 400));
        const recoveredContext = await requestPageContextFromActiveTab();
        if (!recoveredContext) {
          const pauseMessage =
            result.error ??
            "Browser connection lost. Refresh the page, then resume.";
          this.waitingRunId = message.runId;
          this.activeRunId = null;
          runSessionStore.logStepResult(
            message.runId,
            step,
            false,
            pauseMessage,
          );
          runSessionStore.setWaiting(message.runId, pauseMessage);
          void sendToActiveTab({
            type: "ENTER_WAITING_FOR_USER",
            message: pauseMessage,
          });
          this.sendMessage?.({
            type: "ACTION_RESULT",
            runId: message.runId,
            step,
            success: false,
            error: pauseMessage,
            pageContext: undefined,
          });
          return;
        }

        // Content script recovered — retry the step once from fresh page state.
        void sendToActiveTab({
          type: "SET_RUN_PHASE",
          phase: "running",
          message: "Reconnected. Retrying…",
        });
        result = await executeActionStep(step);
      }

      runSessionStore.logStepResult(
        message.runId,
        step,
        result.success,
        result.error,
      );

      if (result.code === "CONNECTION_LOST") {
        const pauseMessage =
          result.error ??
          "Browser connection lost. Refresh the page, then resume.";
        this.waitingRunId = message.runId;
        this.activeRunId = null;
        runSessionStore.setWaiting(message.runId, pauseMessage);
        void sendToActiveTab({
          type: "ENTER_WAITING_FOR_USER",
          message: pauseMessage,
        });
        this.sendMessage?.({
          type: "ACTION_RESULT",
          runId: message.runId,
          step,
          success: false,
          error: pauseMessage,
          pageContext: undefined,
        });
        return;
      }

      await new Promise((resolve) => setTimeout(resolve, 40));
      const pageContext = await requestPageContextFromActiveTab();

      // Fail closed: never claim success without a verified page after DOM actions.
      const success =
        result.success &&
        (step.action === "set_state" ||
          step.action === "wait_for_user" ||
          step.action === "ready_for_payment_link" ||
          pageContext !== undefined);

      this.sendMessage?.({
        type: "ACTION_RESULT",
        runId: message.runId,
        step,
        success,
        error: success
          ? undefined
          : result.error ??
            (pageContext === undefined
              ? "Browser connection lost. Could not verify page state."
              : "Action failed."),
        pageContext,
      });

      if (!success) {
        void sendToActiveTab({
          type: "SET_RUN_PHASE",
          phase: "planning",
          message: result.error ?? "Recovering…",
        });
        return;
      }

      void sendToActiveTab({
        type: "SET_RUN_PHASE",
        phase: "planning",
        message: "Observing page…",
      });
    }
  }

  private finishRun(runId: string): void {
    this.clearAgentSyncWatchdog();
    if (this.activeRunId === runId) {
      this.activeRunId = null;
    }

    if (this.waitingRunId === runId) {
      this.waitingRunId = null;
    }

    if (this.pendingPaymentRunId === runId) {
      this.pendingPaymentRunId = null;
    }

    this.executorMode = "extension_dom";

    void sendToActiveTab({ type: "PARK_CURSOR" });
    void sendToActiveTab({ type: "EXIT_WAITING_MODE" });
    void sendToActiveTab({ type: "HIDE_PAYMENT_HANDOFF" });
    void sendToActiveTab({ type: "SET_STATE", state: "idle" });
    void sendToActiveTab({ type: "SET_RUN_PHASE", phase: "idle" });
  }

  private armAgentSyncWatchdog(runId: string): void {
    this.clearAgentSyncWatchdog();
    this.agentSyncWatchdog = setTimeout(() => {
      if (this.cancelled || this.activeRunId !== runId) {
        return;
      }
      void sendToActiveTab({ type: "PARK_CURSOR" });
      void sendToActiveTab({
        type: "SET_RUN_PHASE",
        phase: "error",
        message:
          "Agent stalled — no progress. Cancel and retry on Razorflow Market (127.0.0.1:3000), or check the LLM provider.",
      });
      void sendToActiveTab({ type: "SET_STATE", state: "paused" });
    }, RunLoopController.AGENT_SYNC_STALL_MS);
  }

  private clearAgentSyncWatchdog(): void {
    if (this.agentSyncWatchdog !== null) {
      clearTimeout(this.agentSyncWatchdog);
      this.agentSyncWatchdog = null;
    }
  }
}

export const runLoopController = new RunLoopController();

type NextActionMessage = Extract<
  BackendToExtensionMessage,
  { type: "NEXT_ACTION" }
>;
