import type {
  ActionStep,
  BackendToExtensionMessage,
  ExtensionToBackendMessage,
  NextActionMessage,
} from "./bridge-protocol";
import type { AgentState, ContentCommand, TargetRole } from "./types";

const AGENT_STATES: AgentState[] = [
  "idle",
  "listening",
  "thinking",
  "acting",
  "paused",
  "waiting_for_user",
];

const TARGET_ROLES: TargetRole[] = ["search", "input", "button", "link"];

export function isStartRunPopupMessage(
  message: unknown,
): message is { type: "START_RUN"; task: string; runId: string } {
  if (!message || typeof message !== "object") {
    return false;
  }

  const payload = message as Record<string, unknown>;
  return (
    payload.type === "START_RUN" &&
    typeof payload.task === "string" &&
    payload.task.trim().length > 0 &&
    typeof payload.runId === "string" &&
    payload.runId.trim().length > 0
  );
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function isOptionalPositiveIndex(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    (typeof value === "number" && Number.isInteger(value) && value > 0)
  );
}

function isActionStep(step: unknown): step is ActionStep {
  if (!step || typeof step !== "object") {
    return false;
  }

  const payload = step as Record<string, unknown>;

  switch (payload.action) {
    case "set_state":
      return (
        typeof payload.state === "string" &&
        AGENT_STATES.includes(payload.state as AgentState)
      );
    case "type_in_element":
      return (
        typeof payload.role === "string" &&
        TARGET_ROLES.includes(payload.role as TargetRole) &&
        typeof payload.text === "string" &&
        isOptionalPositiveIndex(payload.elementIndex) &&
        isOptionalString(payload.matchText)
      );
    case "click_element":
    case "highlight_element":
      return (
        typeof payload.role === "string" &&
        TARGET_ROLES.includes(payload.role as TargetRole) &&
        isOptionalPositiveIndex(payload.elementIndex) &&
        isOptionalString(payload.matchText)
      );
    case "navigate_url":
      return typeof payload.url === "string" && payload.url.trim().length > 0;
    case "wait_for_user":
      return true;
    case "ready_for_payment_link":
      return (
        typeof payload.title === "string" &&
        typeof payload.description === "string" &&
        typeof payload.amountPaise === "number" &&
        typeof payload.currency === "string"
      );
    default:
      return false;
  }
}

export function parseBackendMessage(
  message: unknown,
): BackendToExtensionMessage | null {
  if (!message || typeof message !== "object") {
    return null;
  }

  const payload = message as Record<string, unknown>;

  switch (payload.type) {
    case "NEXT_ACTION":
      if (
        typeof payload.runId !== "string" ||
        !Array.isArray(payload.steps) ||
        !payload.steps.every(isActionStep)
      ) {
        console.warn("[RazorFlow] Dropped NEXT_ACTION — invalid steps", payload);
        return null;
      }

      return payload as unknown as NextActionMessage;
    case "RUN_COMPLETE":
    case "RUN_WAITING_FOR_USER":
    case "RUN_ERROR":
    case "PAYMENT_LINK_CONFIRMATION_REQUIRED":
    case "PAYMENT_LINK_READY":
    case "PAYMENT_LINK_FAILED":
      return payload as unknown as BackendToExtensionMessage;
    case "AGENT_SYNC":
      if (
        typeof payload.runId !== "string" ||
        typeof payload.phase !== "string" ||
        typeof payload.step !== "number"
      ) {
        return null;
      }
      return payload as unknown as BackendToExtensionMessage;
    case "EXECUTOR_MODE":
      if (typeof payload.runId !== "string") {
        return null;
      }
      return payload as unknown as BackendToExtensionMessage;
    default:
      return null;
  }
}

export function actionStepToContentCommand(
  step: ActionStep,
): ContentCommand | null {
  switch (step.action) {
    case "set_state":
      return { type: "SET_STATE", state: step.state };
    case "type_in_element":
      return {
        type: "TYPE_IN_ELEMENT",
        role: step.role,
        text: step.text,
        elementIndex: step.elementIndex ?? undefined,
        matchText: step.matchText ?? undefined,
      };
    case "click_element":
      return {
        type: "CLICK_ELEMENT",
        role: step.role,
        elementIndex: step.elementIndex ?? undefined,
        matchText: step.matchText ?? undefined,
      };
    case "highlight_element":
      return {
        type: "HIGHLIGHT_ELEMENT",
        role: step.role,
        elementIndex: step.elementIndex ?? undefined,
        matchText: step.matchText ?? undefined,
      };
    case "navigate_url":
      return { type: "NAVIGATE_URL", url: step.url };
    case "wait_for_user":
      return { type: "SET_STATE", state: "waiting_for_user" };
    case "ready_for_payment_link":
      return null;
    default:
      return null;
  }
}

export function isExtensionToBackendMessage(
  message: ExtensionToBackendMessage,
): message is ExtensionToBackendMessage {
  return typeof message === "object" && message !== null && "type" in message;
}
