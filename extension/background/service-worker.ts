import type {
  BackgroundToPopupMessage,
  PopupToBackgroundMessage,
} from "../shared/bridge-protocol";
import type { PaymentAuditSnapshot } from "../shared/audit";
import {
  isContentCommand,
  requestPageContextFromActiveTab,
  relayToActiveTab,
} from "../shared/messaging";
import type {
  OverlayCancelMessage,
  OverlayResumeMessage,
} from "../shared/run-timeline";
import type {
  VoiceClientMessage,
  VoiceConfigResponse,
  VoiceTranscriptMessage,
} from "../shared/voice/types";
import { VOICE_INPUT_ENABLED } from "../shared/voice/config";
import { isStartRunPopupMessage } from "../shared/plan";
import { runLoopController } from "./run-loop";
import { runSessionStore } from "./run-session";
import { BridgeWebSocketClient } from "./ws-client";
import { VoiceController } from "./voice-controller";

const bridgeClient = new BridgeWebSocketClient();
bridgeClient.connect();

async function getActiveTabUrl(): Promise<string | undefined> {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });

  return tab?.url;
}

async function resumeWaitingRun(runId: string): Promise<BackgroundToPopupMessage> {
  const pageContext = await requestPageContextFromActiveTab();
  await bridgeClient.resumeRun(runId, pageContext);
  return { type: "RUN_RESUMED", runId };
}

const voiceController = new VoiceController(
  async (task, runId, url, pageContext) => {
    await bridgeClient.startRun(task, runId, url, pageContext);
  },
  async (runId) => {
    await resumeWaitingRun(runId);
  },
  getActiveTabUrl,
);

function isOverlayStartTaskMessage(
  message: unknown,
): message is { type: "OVERLAY_START_TASK"; task: string; runId: string } {
  if (!message || typeof message !== "object") {
    return false;
  }

  const payload = message as Record<string, unknown>;
  return (
    payload.type === "OVERLAY_START_TASK" &&
    typeof payload.task === "string" &&
    payload.task.trim().length > 0 &&
    typeof payload.runId === "string" &&
    payload.runId.trim().length > 0
  );
}

function isPopupMessage(
  message: unknown,
): message is PopupToBackgroundMessage {
  if (!message || typeof message !== "object") {
    return false;
  }

  const payload = message as { type?: string };
  return (
    payload.type === "GET_BRIDGE_STATUS" ||
    payload.type === "GET_RUN_TIMELINE" ||
    payload.type === "GET_PAYMENT_AUDIT" ||
    payload.type === "CANCEL_RUN" ||
    payload.type === "RESUME_RUN" ||
    payload.type === "CONFIRM_PAYMENT_LINK" ||
    payload.type === "DECLINE_PAYMENT_LINK" ||
    isStartRunPopupMessage(message)
  );
}

function isVoiceClientMessage(message: unknown): message is VoiceClientMessage {
  if (!message || typeof message !== "object") {
    return false;
  }

  const type = (message as { type?: string }).type;
  return (
    type === "VOICE_PTT_START" ||
    type === "VOICE_PTT_STOP" ||
    type === "GET_VOICE_CONFIG"
  );
}

function isOverlayHandoffMessage(
  message: unknown,
): message is OverlayResumeMessage | OverlayCancelMessage {
  if (!message || typeof message !== "object") {
    return false;
  }

  const type = (message as { type?: string }).type;
  return type === "OVERLAY_RESUME_RUN" || type === "OVERLAY_CANCEL_RUN";
}

function isOverlayPaymentMessage(message: unknown): boolean {
  if (!message || typeof message !== "object") {
    return false;
  }

  const type = (message as { type?: string }).type;
  return (
    type === "OVERLAY_PAYMENT_CONFIRM" ||
    type === "OVERLAY_PAYMENT_DECLINE" ||
    type === "OVERLAY_PAYMENT_OPEN"
  );
}

chrome.runtime.onMessage.addListener(
  (message: unknown, _sender, sendResponse) => {
    if (isVoiceClientMessage(message)) {
      if (message.type === "GET_VOICE_CONFIG") {
        const response: VoiceConfigResponse = {
          type: "VOICE_CONFIG",
          enabled: voiceController.isEnabled(),
        };
        sendResponse(response);
        return;
      }

      void (async () => {
        if (message.type === "VOICE_PTT_START") {
          await voiceController.handlePttStart(message.source);
          sendResponse({ ok: true });
          return;
        }

        await voiceController.handlePttStop(message.source);
        sendResponse({ ok: true });
      })();

      return true;
    }

    if (
      message &&
      typeof message === "object" &&
      (message as VoiceTranscriptMessage).type === "VOICE_TRANSCRIPT" &&
      (message as VoiceTranscriptMessage).phase === "final"
    ) {
      const transcript = message as VoiceTranscriptMessage;
      void voiceController.handleFinalTranscript(
        transcript.text,
        transcript.source,
      );
      return;
    }

    if (isPopupMessage(message)) {
      if (message.type === "GET_BRIDGE_STATUS") {
        const response: BackgroundToPopupMessage = {
          type: "BRIDGE_STATUS",
          status: bridgeClient.getStatus(),
        };
        sendResponse(response);
        return;
      }

      if (message.type === "GET_RUN_TIMELINE") {
        const response: BackgroundToPopupMessage = {
          type: "RUN_TIMELINE",
          snapshot: runSessionStore.getSnapshot(),
        };
        sendResponse(response);
        return;
      }

      if (message.type === "GET_PAYMENT_AUDIT") {
        void (async () => {
          try {
            const response = await fetch(
              `http://127.0.0.1:8765/audit/payment?runId=${encodeURIComponent(message.runId)}`,
            );
            if (!response.ok) {
              sendResponse({
                type: "TASK_ERROR",
                message: "Could not load payment audit trail.",
              });
              return;
            }

            const payload = (await response.json()) as PaymentAuditSnapshot;
            sendResponse({ type: "PAYMENT_AUDIT", snapshot: payload });
          } catch {
            sendResponse({
              type: "TASK_ERROR",
              message: "Backend audit endpoint unavailable.",
            });
          }
        })();
        return true;
      }

      if (message.type === "CANCEL_RUN") {
        runLoopController.cancelRun();
        const response: BackgroundToPopupMessage = { type: "RUN_CANCELLED" };
        sendResponse(response);
        return;
      }

      if (message.type === "CONFIRM_PAYMENT_LINK") {
        runLoopController.confirmPaymentLink(message.runId);
        sendResponse({ ok: true });
        return;
      }

      if (message.type === "DECLINE_PAYMENT_LINK") {
        runLoopController.declinePaymentLink(message.runId);
        sendResponse({ ok: true });
        return;
      }

      void (async () => {
        try {
          if (message.type === "RESUME_RUN") {
            const response = await resumeWaitingRun(message.runId);
            sendResponse(response);
            return;
          }

          const pageContext = await requestPageContextFromActiveTab();
          if (!pageContext) {
            sendResponse({
              type: "TASK_ERROR",
              message:
                "Cannot reach the page. Open http://127.0.0.1:3000, keep that tab active, then try again.",
            });
            return;
          }

          const url = await getActiveTabUrl();
          await bridgeClient.startRun(
            message.task,
            message.runId,
            url,
            pageContext,
          );

          const response: BackgroundToPopupMessage = {
            type: "TASK_SUBMITTED",
            task: message.task,
            runId: message.runId,
          };
          sendResponse(response);
        } catch (error) {
          const response: BackgroundToPopupMessage = {
            type: "TASK_ERROR",
            message:
              error instanceof Error ? error.message : "Failed to send task.",
          };
          sendResponse(response);
        }
      })();

      return true;
    }

    if (isOverlayPaymentMessage(message)) {
      const type = (message as { type: string }).type;
      const runId =
        runLoopController.getPendingPaymentRunId() ??
        runLoopController.getWaitingRunId();

      if (type === "OVERLAY_PAYMENT_OPEN") {
        const url = runLoopController.getPendingPaymentLinkUrl();
        if (url) {
          void chrome.tabs.create({ url });
        }
        sendResponse({ ok: true });
        return;
      }

      if (!runId) {
        sendResponse({ type: "TASK_ERROR", message: "No payment to confirm." });
        return true;
      }

      if (type === "OVERLAY_PAYMENT_CONFIRM") {
        runLoopController.confirmPaymentLink(runId);
        sendResponse({ ok: true });
        return;
      }

      runLoopController.declinePaymentLink(runId);
      sendResponse({ ok: true });
      return;
    }

    if (isOverlayStartTaskMessage(message)) {
      void (async () => {
        try {
          const pageContext = await requestPageContextFromActiveTab();
          if (!pageContext) {
            sendResponse({
              type: "TASK_ERROR",
              message:
                "Cannot reach this page. Refresh the tab, then try again from the overlay.",
            });
            return;
          }

          const url = await getActiveTabUrl();
          await bridgeClient.startRun(
            message.task,
            message.runId,
            url,
            pageContext,
          );
          sendResponse({ ok: true });
        } catch (error) {
          sendResponse({
            type: "TASK_ERROR",
            message:
              error instanceof Error ? error.message : "Failed to start task.",
          });
        }
      })();

      return true;
    }

    if (isOverlayHandoffMessage(message)) {
      void (async () => {
        if (message.type === "OVERLAY_CANCEL_RUN") {
          runLoopController.cancelRun();
          sendResponse({ type: "RUN_CANCELLED" });
          return;
        }

        const runId = runLoopController.getWaitingRunId();
        if (!runId) {
          sendResponse({
            type: "TASK_ERROR",
            message: "No paused run to resume.",
          });
          return;
        }

        const response = await resumeWaitingRun(runId);
        sendResponse(response);
      })();

      return true;
    }

    if (isContentCommand(message)) {
      relayToActiveTab(message);
    }
  },
);

bridgeClient.subscribe(() => {
  // Connection status is queried by popup on demand.
});

export { VOICE_INPUT_ENABLED };
