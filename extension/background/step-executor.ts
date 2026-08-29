import type { ActionStep } from "../shared/bridge-protocol";
import { actionStepToContentCommand } from "../shared/plan";
import { sendToActiveTab, type TabCommandResult } from "../shared/messaging";

export interface StepExecutionResult {
  success: boolean;
  error?: string;
  code?: TabCommandResult["code"];
  verified?: boolean;
}

export async function executeActionStep(
  step: ActionStep,
): Promise<StepExecutionResult> {
  if (step.action === "ready_for_payment_link") {
    return { success: true, verified: true };
  }

  if (step.action === "wait_for_user") {
    return { success: true, verified: true };
  }

  if (step.action === "wait") {
    const command = actionStepToContentCommand(step);
    if (command) {
      const response = await sendToActiveTab(command);
      if (!response?.ok) {
        return {
          success: false,
          error: response?.error ?? "Wait failed.",
        };
      }
    }
    return { success: true, verified: true };
  }

  if (step.action === "go_back" || step.action === "scroll_page") {
    const command = actionStepToContentCommand(step);
    if (!command) {
      return { success: false, error: "Invalid scroll/back step." };
    }
    const response = await sendToActiveTab(command);
    if (!response?.ok) {
      return {
        success: false,
        code: response?.code ?? "ACTION_FAILED",
        error: response?.error ?? "Step failed.",
      };
    }
    return { success: true, verified: response.verified ?? true };
  }

  if (step.action === "navigate_url") {
    const command = actionStepToContentCommand(step);
    if (!command) {
      return { success: false, error: "Invalid navigate_url step." };
    }
    const response = await sendToActiveTab(command);
    if (!response?.ok) {
      return {
        success: false,
        code: response?.code ?? "ACTION_FAILED",
        error: response?.error ?? "Navigation failed.",
      };
    }
    return { success: true, verified: response.verified ?? true };
  }

  if (step.action === "set_state") {
    const command = actionStepToContentCommand(step);
    if (!command) {
      return { success: false, error: "Unsupported set_state step." };
    }
    const response = await sendToActiveTab(command);
    if (!response?.ok) {
      return {
        success: false,
        code: response?.code ?? "CONNECTION_LOST",
        error:
          response?.error ??
          "Browser connection lost. Reconnecting…",
      };
    }
    return { success: true, verified: true };
  }

  const command = actionStepToContentCommand(step);
  if (!command) {
    return { success: false, error: "Unsupported action step." };
  }

  try {
    const response = await sendToActiveTab(command);
    if (!response) {
      return {
        success: false,
        code: "CONNECTION_LOST",
        error: "Browser connection lost. Reconnecting…",
      };
    }

    if (response.code === "CONNECTION_LOST" || !response.ok) {
      return {
        success: false,
        code: response.code ?? "ACTION_FAILED",
        error:
          response.error ??
          (response.code === "CONNECTION_LOST"
            ? "Browser connection lost. Reconnecting…"
            : "Action failed."),
        verified: false,
      };
    }

    return {
      success: true,
      verified: response.verified ?? true,
    };
  } catch (error) {
    return {
      success: false,
      code: "ACTION_FAILED",
      error: error instanceof Error ? error.message : "Step execution failed.",
      verified: false,
    };
  }
}
