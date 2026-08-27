import type { ContentCommand, TargetRole } from "../shared/types";
import type { GetPageContextResponse, PageContext } from "./page-context";

const TARGET_ROLES: TargetRole[] = ["search", "input", "button", "link"];

export type TabCommandResult = {
  ok: boolean;
  error?: string;
  code?: "CONNECTION_LOST" | "ACTION_FAILED" | "UNSUPPORTED";
  verified?: boolean;
};

function hasTargetRole(message: Record<string, unknown>): boolean {
  return (
    typeof message.role === "string" &&
    TARGET_ROLES.includes(message.role as TargetRole)
  );
}

export function isContentCommand(message: unknown): message is ContentCommand {
  if (!message || typeof message !== "object") {
    return false;
  }

  const payload = message as Record<string, unknown>;
  const { type } = payload;

  switch (type) {
    case "SET_STATE":
    case "MOVE_CURSOR":
    case "SHOW_HIGHLIGHT":
    case "CLEAR_HIGHLIGHT":
    case "PARK_CURSOR":
    case "TOGGLE_OVERLAY":
    case "RUN_DEMO_FLOW":
    case "PING":
      return true;
    case "NAVIGATE_URL":
      return typeof payload.url === "string" && payload.url.trim().length > 0;
    case "ENTER_WAITING_FOR_USER":
      return typeof payload.message === "string";
    case "EXIT_WAITING_MODE":
      return true;
    case "SHOW_PAYMENT_CONFIRMATION":
      return (
        typeof payload.proposal === "object" &&
        payload.proposal !== null &&
        typeof (payload.proposal as { title?: string }).title === "string"
      );
    case "SHOW_PAYMENT_LINK_READY":
      return (
        typeof payload.result === "object" &&
        payload.result !== null &&
        typeof (payload.result as { paymentLinkUrl?: string }).paymentLinkUrl ===
          "string"
      );
    case "HIDE_PAYMENT_HANDOFF":
      return true;
    case "SET_RUN_PHASE":
      return (
        typeof payload.phase === "string" &&
        ["idle", "running", "planning", "complete", "error"].includes(
          payload.phase as string,
        )
      );
    case "HIGHLIGHT_ELEMENT":
    case "CLICK_ELEMENT":
      return (
        hasTargetRole(payload) &&
        (payload.elementIndex === undefined ||
          payload.elementIndex === null ||
          (typeof payload.elementIndex === "number" &&
            payload.elementIndex > 0)) &&
        (payload.matchText === undefined ||
          payload.matchText === null ||
          typeof payload.matchText === "string")
      );
    case "TYPE_IN_ELEMENT":
      return (
        hasTargetRole(payload) &&
        typeof payload.text === "string" &&
        (payload.elementIndex === undefined ||
          payload.elementIndex === null ||
          (typeof payload.elementIndex === "number" &&
            payload.elementIndex > 0)) &&
        (payload.matchText === undefined ||
          payload.matchText === null ||
          typeof payload.matchText === "string")
      );
    default:
      return false;
  }
}

async function pingTab(tabId: number): Promise<boolean> {
  try {
    const response = (await chrome.tabs.sendMessage(tabId, {
      type: "PING",
    })) as { ok?: boolean } | undefined;
    return Boolean(response?.ok);
  } catch {
    return false;
  }
}

export async function ensureContentScriptOnTab(tabId: number): Promise<boolean> {
  if (await pingTab(tabId)) {
    return true;
  }

  try {
    const response = (await chrome.tabs.sendMessage(tabId, {
      type: "GET_PAGE_CONTEXT",
    })) as GetPageContextResponse | undefined;
    if (response?.pageContext) {
      return true;
    }
  } catch {
    // Inject below.
  }

  if (!chrome.scripting) {
    return false;
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content/content-script.js"],
    });
    await chrome.scripting.insertCSS({
      target: { tabId },
      files: ["content/overlay.css"],
    });
    await new Promise((resolve) => setTimeout(resolve, 200));

    if (await pingTab(tabId)) {
      return true;
    }

    // One more inject attempt after a short wait.
    await new Promise((resolve) => setTimeout(resolve, 250));
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content/content-script.js"],
    });
    await new Promise((resolve) => setTimeout(resolve, 200));
    return pingTab(tabId);
  } catch {
    return false;
  }
}

export async function getActiveTabId(): Promise<number | undefined> {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  if (!tab?.id || tab.id < 0) {
    return undefined;
  }
  if (tab.url?.startsWith("chrome://") || tab.url?.startsWith("chrome-extension://")) {
    return undefined;
  }
  return tab.id;
}

export async function sendToActiveTab(
  command: ContentCommand,
): Promise<TabCommandResult | undefined> {
  const tabId = await getActiveTabId();
  if (!tabId) {
    return {
      ok: false,
      code: "CONNECTION_LOST",
      error: "No valid browser tab. Open a normal webpage and try again.",
    };
  }

  const ready = await ensureContentScriptOnTab(tabId);
  if (!ready) {
    return {
      ok: false,
      code: "CONNECTION_LOST",
      error: "Browser connection lost. Reconnecting…",
    };
  }

  try {
    const response = (await chrome.tabs.sendMessage(
      tabId,
      command,
    )) as TabCommandResult | undefined;

    if (!response) {
      return {
        ok: false,
        code: "CONNECTION_LOST",
        error: "Browser connection lost. Reconnecting…",
      };
    }

    return response;
  } catch {
    // One reconnect cycle, then fail closed.
    const reconnected = await ensureContentScriptOnTab(tabId);
    if (!reconnected) {
      return {
        ok: false,
        code: "CONNECTION_LOST",
        error: "Browser connection lost. Refresh the page and resume.",
      };
    }

    try {
      const retry = (await chrome.tabs.sendMessage(
        tabId,
        command,
      )) as TabCommandResult | undefined;
      if (!retry) {
        return {
          ok: false,
          code: "CONNECTION_LOST",
          error: "Browser connection lost. Refresh the page and resume.",
        };
      }
      return retry;
    } catch {
      return {
        ok: false,
        code: "CONNECTION_LOST",
        error: "Browser connection lost. Refresh the page and resume.",
      };
    }
  }
}

export function relayToActiveTab(command: ContentCommand): void {
  void sendToActiveTab(command);
}

export async function requestPageContextFromActiveTab(): Promise<
  PageContext | undefined
> {
  const tabId = await getActiveTabId();
  if (!tabId) {
    return undefined;
  }

  const ready = await ensureContentScriptOnTab(tabId);
  if (!ready) {
    return undefined;
  }

  try {
    const response = (await chrome.tabs.sendMessage(tabId, {
      type: "GET_PAGE_CONTEXT",
    })) as GetPageContextResponse | undefined;
    return response?.pageContext;
  } catch {
    const reconnected = await ensureContentScriptOnTab(tabId);
    if (!reconnected) {
      return undefined;
    }
    try {
      const response = (await chrome.tabs.sendMessage(tabId, {
        type: "GET_PAGE_CONTEXT",
      })) as GetPageContextResponse | undefined;
      return response?.pageContext;
    } catch {
      return undefined;
    }
  }
}
