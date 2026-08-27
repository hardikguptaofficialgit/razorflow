import type { AgentState, ContentCommand } from "../shared/types";
import type {
  BackgroundToPopupMessage,
  BridgeConnectionStatus,
  PopupToBackgroundMessage,
} from "../shared/bridge-protocol";
import { formatAuditEventType, type PaymentAuditEntry } from "../shared/audit";
import {
  DEMO_HINT,
  DEMO_MODE_ENABLED,
  DEMO_STORE_URL,
  DEMO_TASK,
} from "../shared/demo-config";
import { formatAmount } from "../shared/payment-link";
import type {
  PaymentLinkProposal,
  PaymentLinkResult,
} from "../shared/payment-link";
import type {
  RunTimelineSnapshot,
  RunTimelineUpdateMessage,
  TimelineEvent,
} from "../shared/run-timeline";
import { presentTimelineEvent } from "../shared/timeline-present";
import { bindPushToTalkButton } from "../shared/voice/ptt";
import type {
  VoiceConfigResponse,
  VoiceStatusMessage,
  VoiceTranscriptMessage,
} from "../shared/voice/types";

function sendCommand(command: ContentCommand): void {
  void chrome.runtime.sendMessage(command);
}

function sendPopupMessage(
  message: PopupToBackgroundMessage,
): Promise<BackgroundToPopupMessage | undefined> {
  return chrome.runtime.sendMessage(message);
}

function setBridgeStatus(status: BridgeConnectionStatus): void {
  const statusElement = document.getElementById("bridge-status");
  if (!statusElement) {
    return;
  }

  const labels: Record<BridgeConnectionStatus, string> = {
    connected: "Agent backend connected",
    connecting: "Agent backend connecting…",
    disconnected: "Agent backend disconnected — retrying",
  };

  statusElement.dataset.status = status;
  statusElement.textContent = labels[status];
}

function setTaskFeedback(message: string, isError = false): void {
  const feedback = document.getElementById("task-feedback");
  if (!feedback) {
    return;
  }

  feedback.hidden = false;
  feedback.textContent = message;
  feedback.style.color = isError ? "#b91c1c" : "#71717a";
}

function setVoiceFeedback(
  message: string,
  options: { error?: boolean; recording?: boolean } = {},
): void {
  const feedback = document.getElementById("voice-feedback");
  if (!feedback) {
    return;
  }

  feedback.textContent = message;
  feedback.dataset.error = options.error ? "true" : "false";
  feedback.dataset.recording = options.recording ? "true" : "false";
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderRunContext(snapshot: RunTimelineSnapshot): void {
  const context = document.getElementById("run-context");
  if (!context) {
    return;
  }

  if (!snapshot.context.runId) {
    context.textContent = "No active run.";
    return;
  }

  const statusLabel =
    snapshot.context.status === "waiting_for_user"
      ? "Paused — waiting for you"
      : snapshot.context.status === "active"
        ? "Running"
        : "Idle";

  context.textContent = `${statusLabel} · ${snapshot.context.task ?? "Task"}`;
}

function renderTimeline(snapshot: RunTimelineSnapshot): void {
  const list = document.getElementById("run-timeline");
  const empty = document.getElementById("timeline-empty");
  const waitingBanner = document.getElementById("waiting-banner");
  const waitingMessage = document.getElementById("waiting-banner-message");

  if (!list || !empty) {
    return;
  }

  list.replaceChildren();
  renderRunContext(snapshot);

  for (const event of snapshot.events) {
    list.appendChild(createTimelineItem(event));
  }

  empty.hidden = snapshot.events.length > 0;

  if (waitingBanner && waitingMessage) {
    const isWaiting = snapshot.context.status === "waiting_for_user";
    waitingBanner.hidden = !isWaiting;
    waitingMessage.textContent =
      snapshot.context.waitingMessage ??
      "Complete the step on the page, then resume.";
  }

  void refreshPaymentAudit(snapshot.context.runId);
}

function createTimelineItem(event: TimelineEvent): HTMLLIElement {
  const presentation = presentTimelineEvent(event.kind, event.label);
  const item = document.createElement("li");
  item.dataset.kind = event.kind;

  const kind = document.createElement("span");
  kind.className = `timeline-kind timeline-kind--${event.kind}`;
  kind.textContent = presentation.badge;

  const label = document.createElement("span");
  label.className = "timeline-label";
  label.textContent = presentation.title;

  const time = document.createElement("time");
  time.className = "timeline-time";
  time.dateTime = new Date(event.timestamp).toISOString();
  time.textContent = formatTime(event.timestamp);

  item.append(kind, label, time);
  return item;
}

function renderPaymentAudit(entries: PaymentAuditEntry[]): void {
  const list = document.getElementById("payment-audit");
  const empty = document.getElementById("audit-empty");
  if (!list || !empty) {
    return;
  }

  list.replaceChildren();

  for (const entry of entries) {
    const item = document.createElement("li");
    item.dataset.eventType = entry.eventType;

    const badge = document.createElement("span");
    badge.className = "audit-kind";
    badge.textContent = formatAuditEventType(entry.eventType);

    const message = document.createElement("span");
    message.className = "audit-message";
    message.textContent = entry.message;

    const time = document.createElement("time");
    time.className = "audit-time";
    time.textContent = entry.timestamp
      ? new Date(entry.timestamp).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      : "";

    item.append(badge, message, time);
    list.appendChild(item);
  }

  empty.hidden = entries.length > 0;
}

let pendingPaymentProposal: PaymentLinkProposal | null = null;
let readyPaymentLink: PaymentLinkResult | null = null;
let pendingPaymentRunId: string | null = null;
let currentRunId: string | null = null;

function renderPaymentSection(): void {
  const section = document.getElementById("payment-section");
  const summary = document.getElementById("payment-summary");
  const confirmButton = document.getElementById("confirm-payment-link");
  const declineButton = document.getElementById("decline-payment-link");
  const openButton = document.getElementById("open-payment-link");

  if (!section || !summary || !confirmButton || !declineButton || !openButton) {
    return;
  }

  if (readyPaymentLink) {
    section.hidden = false;
    confirmButton.hidden = true;
    declineButton.hidden = true;
    openButton.hidden = false;
    summary.textContent = `Payment link ready — ${formatAmount(
      readyPaymentLink.amountPaise,
      readyPaymentLink.currency,
    )}. ${readyPaymentLink.description}`;
    return;
  }

  if (pendingPaymentProposal && pendingPaymentRunId) {
    section.hidden = false;
    confirmButton.hidden = false;
    declineButton.hidden = false;
    openButton.hidden = true;
    summary.textContent = `Confirm Razorpay payment link for ${pendingPaymentProposal.title} (${formatAmount(
      pendingPaymentProposal.amountPaise,
      pendingPaymentProposal.currency,
    )}).`;
    return;
  }

  section.hidden = true;
}

async function refreshBridgeStatus(): Promise<void> {
  const response = await sendPopupMessage({ type: "GET_BRIDGE_STATUS" });
  if (response?.type === "BRIDGE_STATUS") {
    setBridgeStatus(response.status);
  }

  await refreshConfigHint();
}

async function refreshConfigHint(): Promise<void> {
  const hint = document.getElementById("config-hint");
  if (!hint) {
    return;
  }

  try {
    const response = await fetch("http://127.0.0.1:8765/health");
    if (!response.ok) {
      hint.hidden = true;
      return;
    }

    const payload = (await response.json()) as {
      groqConfigured?: boolean;
      razorpayConfigured?: boolean;
      plannerMode?: string;
    };

    if (!payload.groqConfigured) {
      hint.hidden = false;
      hint.textContent =
        "Add GROQ_API_KEY to .env and restart the backend to enable planning.";
      return;
    }

    if (!payload.razorpayConfigured) {
      hint.hidden = false;
      hint.textContent =
        "Payments need Razorpay test keys in .env before checkout demo.";
      return;
    }

    hint.hidden = true;
  } catch {
    hint.hidden = true;
  }
}

function waitForTabComplete(tabId: number, timeoutMs = 8000): Promise<void> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, timeoutMs);

    const listener = (
      updatedTabId: number,
      info: chrome.tabs.TabChangeInfo,
    ): void => {
      if (updatedTabId === tabId && info.status === "complete") {
        window.clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };

    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function ensureDemoStoreTabActive(): Promise<void> {
  const storePattern = /^https?:\/\/(localhost|127\.0\.0\.1):3000(\/|$|\?)/;
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const storeTab = tabs.find((tab) => tab.url && storePattern.test(tab.url));

  if (storeTab?.id) {
    await chrome.tabs.update(storeTab.id, { active: true });
    return;
  }

  const tab = await chrome.tabs.create({ url: DEMO_STORE_URL, active: true });
  if (tab.id) {
    await waitForTabComplete(tab.id);
  }
}

async function refreshTimeline(): Promise<void> {
  const response = await sendPopupMessage({ type: "GET_RUN_TIMELINE" });
  if (response?.type === "RUN_TIMELINE") {
    currentRunId = response.snapshot.context.runId;
    renderTimeline(response.snapshot);
  }
}

async function refreshPaymentAudit(runId: string | null = currentRunId): Promise<void> {
  if (!runId) {
    renderPaymentAudit([]);
    return;
  }

  const response = await sendPopupMessage({
    type: "GET_PAYMENT_AUDIT",
    runId,
  });

  if (response?.type === "PAYMENT_AUDIT") {
    renderPaymentAudit(response.snapshot.entries);
  }
}

async function startTask(task: string): Promise<void> {
  const runId = crypto.randomUUID();
  currentRunId = runId;
  const response = await sendPopupMessage({
    type: "START_RUN",
    task,
    runId,
  });

  if (response?.type === "TASK_SUBMITTED") {
    setTaskFeedback("RazorFlow is working on your task.");
    await refreshTimeline();
    return;
  }

  if (response?.type === "TASK_ERROR") {
    setTaskFeedback(response.message, true);
    await refreshBridgeStatus();
  }
}

async function resumeWaitingRun(): Promise<void> {
  const timeline = await sendPopupMessage({ type: "GET_RUN_TIMELINE" });
  const runId =
    timeline?.type === "RUN_TIMELINE" &&
    timeline.snapshot.context.status === "waiting_for_user"
      ? timeline.snapshot.context.runId
      : null;

  if (!runId) {
    setTaskFeedback("No paused run to resume.", true);
    return;
  }

  const response = await sendPopupMessage({ type: "RESUME_RUN", runId });

  if (response?.type === "RUN_RESUMED") {
    setTaskFeedback("Run resumed.");
    await refreshTimeline();
    return;
  }

  if (response?.type === "TASK_ERROR") {
    setTaskFeedback(response.message, true);
  }
}

function applyDemoMode(): void {
  const demoBanner = document.getElementById("demo-banner");
  const devTools = document.getElementById("dev-tools");
  const taskInput = document.getElementById("task-input") as HTMLInputElement | null;
  const demoHint = document.getElementById("demo-hint");

  if (demoHint) {
    demoHint.textContent = DEMO_HINT;
  }

  if (taskInput) {
    taskInput.value = DEMO_TASK;
  }

  if (DEMO_MODE_ENABLED) {
    demoBanner?.classList.add("demo-banner--active");
    devTools?.setAttribute("hidden", "true");
    document.body.classList.add("demo-mode");
    return;
  }

  demoBanner?.setAttribute("hidden", "true");
}

document.querySelectorAll<HTMLButtonElement>("[data-state]").forEach((button) => {
  button.addEventListener("click", () => {
    const state = button.dataset.state as AgentState;
    sendCommand({ type: "SET_STATE", state });
  });
});

document.getElementById("start-demo-run")?.addEventListener("click", async () => {
  setTaskFeedback("Opening demo store…");
  await ensureDemoStoreTabActive();
  await startTask(DEMO_TASK);
});

document.getElementById("open-demo-store")?.addEventListener("click", () => {
  void chrome.tabs.create({ url: DEMO_STORE_URL });
});

document.getElementById("run-task")?.addEventListener("click", async () => {
  const input = document.getElementById("task-input") as HTMLInputElement | null;
  const task = input?.value.trim() ?? "";

  if (!task) {
    setTaskFeedback("Describe a task before running.", true);
    return;
  }

  await startTask(task);
});

document.getElementById("resume-run")?.addEventListener("click", () => {
  void resumeWaitingRun();
});

document.getElementById("cancel-run")?.addEventListener("click", async () => {
  const response = await sendPopupMessage({ type: "CANCEL_RUN" });

  if (response?.type === "RUN_CANCELLED") {
    setTaskFeedback("Run cancelled.");
    pendingPaymentProposal = null;
    pendingPaymentRunId = null;
    readyPaymentLink = null;
    renderPaymentSection();
    await refreshTimeline();
  }
});

document.getElementById("move-cursor")?.addEventListener("click", () => {
  sendCommand({ type: "MOVE_CURSOR", x: 420, y: 280 });
});

document.getElementById("show-highlight")?.addEventListener("click", () => {
  sendCommand({
    type: "SHOW_HIGHLIGHT",
    x: 120,
    y: 180,
    width: 240,
    height: 96,
  });
});

document.getElementById("run-demo-flow")?.addEventListener("click", () => {
  sendCommand({ type: "RUN_DEMO_FLOW", text: "shampoo" });
});

document.getElementById("decline-payment-link")?.addEventListener("click", async () => {
  if (!pendingPaymentRunId) {
    return;
  }

  await sendPopupMessage({
    type: "DECLINE_PAYMENT_LINK",
    runId: pendingPaymentRunId,
  });
  pendingPaymentProposal = null;
  pendingPaymentRunId = null;
  renderPaymentSection();
});

document.getElementById("confirm-payment-link")?.addEventListener("click", async () => {
  if (!pendingPaymentRunId) {
    return;
  }

  await sendPopupMessage({
    type: "CONFIRM_PAYMENT_LINK",
    runId: pendingPaymentRunId,
  });
  setTaskFeedback("Creating payment link via policy gate…");
});

document.getElementById("open-payment-link")?.addEventListener("click", () => {
  if (readyPaymentLink?.paymentLinkUrl) {
    void chrome.tabs.create({ url: readyPaymentLink.paymentLinkUrl });
  }
});

document.getElementById("toggle-overlay")?.addEventListener("click", () => {
  sendCommand({ type: "TOGGLE_OVERLAY" });
});

document.getElementById("refresh-audit")?.addEventListener("click", () => {
  void refreshPaymentAudit();
});

async function initVoiceUi(): Promise<void> {
  const section = document.getElementById("voice-section");
  const button = document.getElementById("voice-ptt") as HTMLButtonElement | null;
  if (!section || !button) {
    return;
  }

  const config = (await chrome.runtime.sendMessage({
    type: "GET_VOICE_CONFIG",
  })) as VoiceConfigResponse | undefined;

  if (!config?.enabled) {
    section.hidden = true;
    return;
  }

  bindPushToTalkButton(button, "popup", (text) => {
    setVoiceFeedback(text, { recording: true });
  });
}

applyDemoMode();
void initVoiceUi();
void refreshBridgeStatus();
void refreshTimeline();

window.setInterval(() => {
  void refreshBridgeStatus();
}, 2000);

chrome.runtime.onMessage.addListener((message: unknown) => {
  if (
    typeof message === "object" &&
    message !== null &&
    (message as RunTimelineUpdateMessage).type === "RUN_TIMELINE_UPDATE"
  ) {
    const snapshot = (message as RunTimelineUpdateMessage).snapshot;
    currentRunId = snapshot.context.runId;
    renderTimeline(snapshot);
    return;
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "RUN_WAITING_FOR_USER"
  ) {
    void refreshTimeline();
    return;
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "PAYMENT_LINK_CONFIRMATION_REQUIRED"
  ) {
    const payload = message as {
      runId: string;
      proposal: PaymentLinkProposal;
    };
    pendingPaymentRunId = payload.runId;
    currentRunId = payload.runId;
    pendingPaymentProposal = payload.proposal;
    readyPaymentLink = null;
    renderPaymentSection();
    void refreshTimeline();
    return;
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "PAYMENT_LINK_READY"
  ) {
    const payload = message as PaymentLinkResult & { runId: string };
    readyPaymentLink = {
      paymentLinkUrl: payload.paymentLinkUrl,
      amountPaise: payload.amountPaise,
      currency: payload.currency,
      description: payload.description,
      referenceId: payload.referenceId,
    };
    pendingPaymentProposal = null;
    renderPaymentSection();
    void refreshTimeline();
    void refreshPaymentAudit(payload.runId);
    return;
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "PAYMENT_LINK_FAILED"
  ) {
    const payload = message as { message: string; runId?: string };
    setTaskFeedback(payload.message, true);
    void refreshTimeline();
    void refreshPaymentAudit(payload.runId ?? currentRunId);
    return;
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as VoiceStatusMessage).type === "VOICE_STATUS"
  ) {
    const status = message as VoiceStatusMessage;
    if (status.source && status.source !== "popup") {
      return;
    }

    if (status.state === "error") {
      setVoiceFeedback(status.text ?? "Voice input failed.", { error: true });
      return;
    }

    if (status.state === "recording" || status.state === "loading_model") {
      setVoiceFeedback(status.text ?? "Listening…", { recording: true });
      return;
    }

    if (status.state === "transcribing" || status.state === "routing") {
      setVoiceFeedback(status.text ?? "Processing…");
      return;
    }

    if (status.text) {
      setVoiceFeedback(status.text);
    }

    if (status.state === "idle" && status.text?.startsWith("Started:")) {
      void refreshTimeline();
      setTaskFeedback("Task started from voice.");
    }

    if (status.state === "idle" && status.text === "Resumed run.") {
      void refreshTimeline();
      setTaskFeedback("Run resumed from voice.");
    }
  }

  if (
    typeof message === "object" &&
    message !== null &&
    (message as VoiceTranscriptMessage).type === "VOICE_TRANSCRIPT"
  ) {
    const transcript = message as VoiceTranscriptMessage;
    if (transcript.source !== "popup") {
      return;
    }

    setVoiceFeedback(
      transcript.phase === "partial"
        ? transcript.text
        : `Heard: "${transcript.text}"`,
      { recording: transcript.phase === "partial" },
    );
  }
});
