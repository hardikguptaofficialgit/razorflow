import type { ContentCommand } from "../shared/types";
import { isContentCommand } from "../shared/messaging";
import { isGetPageContextRequest } from "../shared/page-context";
import type { ActionPlayer } from "./action-playback";
import { extractPageContext } from "./page-context";
import type { OverlayController } from "./overlay-state";

type ContentCommandResult = {
  ok: boolean;
  error?: string;
  verified?: boolean;
  code?: "CONNECTION_LOST" | "ACTION_FAILED" | "UNSUPPORTED";
};

async function runContentCommand(
  controller: OverlayController,
  actionPlayer: ActionPlayer,
  command: ContentCommand,
): Promise<ContentCommandResult> {
  switch (command.type) {
    case "PING":
      return { ok: true, verified: true };
    case "SET_STATE":
      controller.setState(command.state);
      return { ok: true };
    case "MOVE_CURSOR":
      controller.moveCursor(command.x, command.y);
      return { ok: true };
    case "SHOW_HIGHLIGHT":
      controller.showHighlight({
        x: command.x,
        y: command.y,
        width: command.width,
        height: command.height,
      });
      return { ok: true };
    case "CLEAR_HIGHLIGHT":
      controller.clearHighlight();
      return { ok: true };
    case "PARK_CURSOR":
      controller.parkCursor();
      return { ok: true };
    case "TOGGLE_OVERLAY":
      controller.toggleOverlay(command.visible);
      return { ok: true };
    case "HIGHLIGHT_ELEMENT": {
      const outcome = await actionPlayer.highlightElement(
        command.role,
        command.elementIndex,
        command.matchText,
      );
      return {
        ok: outcome.ok,
        error: outcome.error,
        verified: outcome.verified,
        code: outcome.ok ? undefined : "ACTION_FAILED",
      };
    }
    case "CLICK_ELEMENT": {
      const outcome = await actionPlayer.clickElement(
        command.role,
        command.elementIndex,
        command.matchText,
      );
      return {
        ok: outcome.ok,
        error: outcome.error,
        verified: outcome.verified,
        code: outcome.ok ? undefined : "ACTION_FAILED",
      };
    }
    case "TYPE_IN_ELEMENT": {
      const outcome = await actionPlayer.typeInElement(
        command.role,
        command.text,
        command.elementIndex,
        command.matchText,
      );
      return {
        ok: outcome.ok,
        error: outcome.error,
        verified: outcome.verified,
        code: outcome.ok ? undefined : "ACTION_FAILED",
      };
    }
    case "NAVIGATE_URL": {
      try {
        const target = new URL(command.url, window.location.origin);
        window.location.assign(target.toString());
        return { ok: true, verified: true };
      } catch (error) {
        return {
          ok: false,
          error: error instanceof Error ? error.message : "Navigation failed.",
          code: "ACTION_FAILED",
        };
      }
    }
    case "SCROLL_PAGE": {
      const amount = command.amountPx ?? 600;
      if (command.direction === "top") {
        window.scrollTo(0, 0);
      } else if (command.direction === "bottom") {
        window.scrollTo(0, document.documentElement.scrollHeight);
      } else if (command.direction === "up") {
        window.scrollBy(0, -amount);
      } else {
        window.scrollBy(0, amount);
      }
      return { ok: true, verified: true };
    }
    case "WAIT":
      await new Promise((resolve) => setTimeout(resolve, command.durationMs ?? 300));
      return { ok: true, verified: true };
    case "GO_BACK":
      window.history.back();
      return { ok: true, verified: true };
    case "RUN_DEMO_FLOW": {
      const outcome = await actionPlayer.runDemoFlow(command.text ?? "shampoo");
      return {
        ok: outcome.ok,
        error: outcome.error,
        verified: outcome.verified,
        code: outcome.ok ? undefined : "ACTION_FAILED",
      };
    }
    case "ENTER_WAITING_FOR_USER":
      controller.enterWaitingForUser(command.message);
      return { ok: true };
    case "EXIT_WAITING_MODE":
      controller.exitWaitingMode();
      controller.setState("thinking");
      return { ok: true };
    case "SHOW_PAYMENT_CONFIRMATION":
      controller.showPaymentConfirmation(command.proposal);
      return { ok: true };
    case "SHOW_PAYMENT_LINK_READY":
      controller.showPaymentLinkReady(command.result);
      return { ok: true };
    case "HIDE_PAYMENT_HANDOFF":
      controller.hidePaymentHandoff();
      return { ok: true };
    case "SET_RUN_PHASE":
      controller.setRunPhase(command.phase, command.message);
      return { ok: true };
    default:
      return {
        ok: false,
        error: "Unsupported content command.",
        code: "UNSUPPORTED",
      };
  }
}

export async function handleContentCommand(
  controller: OverlayController,
  actionPlayer: ActionPlayer,
  command: ContentCommand,
): Promise<ContentCommandResult> {
  try {
    return await runContentCommand(controller, actionPlayer, command);
  } catch (error) {
    return {
      ok: false,
      code: "ACTION_FAILED",
      error: error instanceof Error ? error.message : "Step execution failed.",
    };
  }
}

export function registerMessageListener(
  controller: OverlayController,
  actionPlayer: ActionPlayer,
): void {
  chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
    if (isGetPageContextRequest(message)) {
      sendResponse({ pageContext: extractPageContext() });
      return;
    }

    if (!isContentCommand(message)) {
      return;
    }

    void handleContentCommand(controller, actionPlayer, message)
      .then((result) => {
        sendResponse(result);
      })
      .catch((error: unknown) => {
        sendResponse({
          ok: false,
          code: "ACTION_FAILED",
          error:
            error instanceof Error ? error.message : "Step execution failed.",
        });
      });

    return true;
  });
}
