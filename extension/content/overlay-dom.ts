import type { AgentState } from "../shared/types";
import { getBrandLogoUrl, getDockTextureUrl } from "../shared/brand";
import { OVERLAY_ROOT_ID } from "../shared/types";

export type OverlayRunPhase =
  | "running"
  | "planning"
  | "complete"
  | "error"
  | "idle";

export interface OverlayElements {
  root: HTMLDivElement;
  viewportFrame: HTMLDivElement;
  cursor: HTMLDivElement;
  highlight: HTMLDivElement;
  commandDock: HTMLDivElement;
  statusLabel: HTMLSpanElement;
  textToggleButton: HTMLButtonElement;
  textInput: HTMLInputElement;
  sendTaskButton: HTMLButtonElement;
  collapseTextButton: HTMLButtonElement;
  composePanel: HTMLDivElement;
  voiceButton: HTMLButtonElement;
  toast: HTMLDivElement;
  waitingPanel: HTMLDivElement;
  waitingMessage: HTMLParagraphElement;
  paymentPanel: HTMLDivElement;
  paymentTitle: HTMLParagraphElement;
  paymentDescription: HTMLParagraphElement;
  paymentAmount: HTMLParagraphElement;
  paymentReadyPanel: HTMLDivElement;
  paymentReadyDescription: HTMLParagraphElement;
  paymentReadyAmount: HTMLParagraphElement;
  paymentReadyReference: HTMLParagraphElement;
}

const STATE_LABELS: Record<AgentState, string> = {
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking",
  acting: "Acting",
  paused: "Paused",
  waiting_for_user: "Your turn",
};

const ACTIVE_STATES: AgentState[] = [
  "listening",
  "thinking",
  "acting",
  "paused",
  "waiting_for_user",
];

export function createOverlayRoot(): OverlayElements {
  const existing = document.getElementById(OVERLAY_ROOT_ID);
  if (existing) {
    existing.remove();
  }

  const root = document.createElement("div");
  root.id = OVERLAY_ROOT_ID;
  root.setAttribute("data-visible", "true");
  root.setAttribute("data-state", "idle");
  root.setAttribute("data-run-phase", "idle");
  root.setAttribute("data-takeover", "false");
  root.setAttribute("data-agent-active", "false");

  root.innerHTML = `
    <div class="rf-viewport-frame" aria-hidden="true"></div>
    <div class="rf-highlight" aria-hidden="true"></div>

    <div class="rf-cursor" aria-hidden="true">
      <svg class="rf-cursor-pointer" width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M1.2 1.2 L1.2 16.8 L6.4 12.4 L10.6 20.8 L13.5 19.3 L9.3 10.9 L16.4 10.9 Z"
          fill="#ffffff"
          stroke="#000000"
          stroke-width="1.15"
          stroke-linejoin="round"
        />
      </svg>
      <span class="rf-cursor-ring" aria-hidden="true"></span>
    </div>

    <div class="rf-toast" hidden role="status" aria-live="polite"></div>

    <div class="rf-waiting-panel" hidden>
      <p class="rf-panel-kicker">Handoff</p>
      <p class="rf-waiting-message"></p>
      <div class="rf-panel-actions">
        <button type="button" class="rf-btn rf-btn-primary" data-action="resume">Resume</button>
        <button type="button" class="rf-btn rf-btn-ghost" data-action="cancel">Cancel</button>
      </div>
    </div>

    <div class="rf-payment-panel" hidden>
      <p class="rf-panel-kicker">Confirm Payment</p>
      <p class="rf-payment-title"></p>
      <p class="rf-payment-description"></p>
      <p class="rf-payment-amount"></p>
      <div class="rf-panel-actions">
        <button type="button" class="rf-btn rf-btn-primary" data-action="confirm-payment">Create payment link</button>
        <button type="button" class="rf-btn rf-btn-ghost" data-action="decline-payment">Cancel</button>
      </div>
    </div>

    <div class="rf-payment-ready-panel" hidden>
      <p class="rf-panel-kicker">Payment Ready</p>
      <p class="rf-payment-ready-description"></p>
      <p class="rf-payment-ready-amount"></p>
      <p class="rf-payment-ready-reference"></p>
      <div class="rf-panel-actions">
        <button type="button" class="rf-btn rf-btn-primary" data-action="open-payment-link">Open payment link</button>
      </div>
    </div>

    <div class="rf-command-dock" data-input-expanded="false">
      <div class="rf-dock-brand">
        <div class="rf-brand-icon-wrapper">
          <img class="rf-brand-logo" alt="RazorFlow" width="28" height="28" />
        </div>
        <span class="rf-brand-name">RazorFlow</span>
      </div>

      <span class="rf-dock-sep rf-dock-compact-only" aria-hidden="true"></span>

      <div class="rf-dock-status rf-dock-compact-only" data-state="idle">
        <span class="rf-status-icon" aria-hidden="true"></span>
        <span class="rf-status-label">Ready</span>
      </div>

      <span class="rf-dock-sep rf-dock-compact-only" aria-hidden="true"></span>

      <button
        type="button"
        class="rf-dock-btn rf-dock-btn--icon rf-dock-compact-only"
        data-action="toggle-text"
        aria-label="Type a task"
        title="Type a task"
      >
      <!-- Optional: Insert your keyboard icon SVG here -->
      </button>

      <div class="rf-dock-compose">
        <input
          type="text"
          class="rf-dock-input"
          placeholder="Ask RazorFlow to shop, search, or checkout…"
          autocomplete="off"
          spellcheck="false"
          enterkeyhint="go"
          aria-label="Task for RazorFlow"
        />
        <button
          type="button"
          class="rf-dock-btn rf-dock-btn--accent"
          data-action="send-task"
          aria-label="Run task"
          title="Run task"
        ></button>
        <button
          type="button"
          class="rf-dock-btn rf-dock-btn--icon"
          data-action="collapse-text"
          aria-label="Close input"
          title="Close"
        ></button>
      </div>

      <span class="rf-dock-sep rf-dock-voice-sep" aria-hidden="true"></span>

      <button
        type="button"
        class="rf-dock-btn rf-dock-btn--voice rf-dock-btn--icon"
        data-action="voice"
        aria-label="Hold to speak"
        title="Hold to speak"
      >
      <!-- Optional: Insert your mic icon SVG here -->
      </button>
    </div>
  `;

  document.documentElement.appendChild(root);
  applyOverlayAssets(root);
  return collectOverlayElements(root);
}

function applyOverlayAssets(root: HTMLDivElement): void {
  root.style.setProperty(
    "--rf-dock-texture",
    `url("${getDockTextureUrl()}")`,
  );
  ensureBrandLogo(root);
}

function ensureBrandLogo(root: HTMLDivElement): void {
  const logo = root.querySelector(".rf-brand-logo") as HTMLImageElement | null;
  if (!logo) {
    return;
  }

  const logoUrl = getBrandLogoUrl();
  if (logo.src !== logoUrl) {
    logo.src = logoUrl;
  }
}

function collectOverlayElements(root: HTMLDivElement): OverlayElements {
  return {
    root,
    viewportFrame: root.querySelector(".rf-viewport-frame") as HTMLDivElement,
    cursor: root.querySelector(".rf-cursor") as HTMLDivElement,
    highlight: root.querySelector(".rf-highlight") as HTMLDivElement,
    commandDock: root.querySelector(".rf-command-dock") as HTMLDivElement,
    statusLabel: root.querySelector(".rf-status-label") as HTMLSpanElement,
    textToggleButton: root.querySelector(
      '[data-action="toggle-text"]',
    ) as HTMLButtonElement,
    textInput: root.querySelector(".rf-dock-input") as HTMLInputElement,
    sendTaskButton: root.querySelector(
      '[data-action="send-task"]',
    ) as HTMLButtonElement,
    collapseTextButton: root.querySelector(
      '[data-action="collapse-text"]',
    ) as HTMLButtonElement,
    composePanel: root.querySelector(".rf-dock-compose") as HTMLDivElement,
    voiceButton: root.querySelector(
      '[data-action="voice"]',
    ) as HTMLButtonElement,
    toast: root.querySelector(".rf-toast") as HTMLDivElement,
    waitingPanel: root.querySelector(".rf-waiting-panel") as HTMLDivElement,
    waitingMessage: root.querySelector(
      ".rf-waiting-message",
    ) as HTMLParagraphElement,
    paymentPanel: root.querySelector(".rf-payment-panel") as HTMLDivElement,
    paymentTitle: root.querySelector(".rf-payment-title") as HTMLParagraphElement,
    paymentDescription: root.querySelector(
      ".rf-payment-description",
    ) as HTMLParagraphElement,
    paymentAmount: root.querySelector(
      ".rf-payment-amount",
    ) as HTMLParagraphElement,
    paymentReadyPanel: root.querySelector(
      ".rf-payment-ready-panel",
    ) as HTMLDivElement,
    paymentReadyDescription: root.querySelector(
      ".rf-payment-ready-description",
    ) as HTMLParagraphElement,
    paymentReadyAmount: root.querySelector(
      ".rf-payment-ready-amount",
    ) as HTMLParagraphElement,
    paymentReadyReference: root.querySelector(
      ".rf-payment-ready-reference",
    ) as HTMLParagraphElement,
  };
}

export function applyAgentStateToDom(
  elements: OverlayElements,
  state: AgentState,
  label?: string,
): void {
  elements.root.setAttribute("data-state", state);
  elements.commandDock
    .querySelector(".rf-dock-status")
    ?.setAttribute("data-state", state);
  elements.statusLabel.textContent = label ?? STATE_LABELS[state];
  elements.root.setAttribute(
    "data-agent-active",
    ACTIVE_STATES.includes(state) ? "true" : "false",
  );
}

export function applyRunPhaseToDom(
  elements: OverlayElements,
  phase: OverlayRunPhase,
  message?: string,
): void {
  elements.root.setAttribute("data-run-phase", phase);

  const showToast = (text: string, error = false): void => {
    elements.toast.hidden = false;
    elements.toast.textContent = text;
    if (error) {
      elements.toast.dataset.error = "true";
    } else {
      elements.toast.removeAttribute("data-error");
    }
    window.setTimeout(() => {
      if (elements.toast.textContent === text) {
        elements.toast.hidden = true;
        elements.toast.textContent = "";
        elements.toast.removeAttribute("data-error");
      }
    }, 2800);
  };

  if (phase === "planning") {
    elements.statusLabel.textContent = message ?? "Planning";
    elements.root.setAttribute("data-agent-active", "true");
    if (message) {
      showToast(message);
    }
    return;
  }

  if (phase === "running" || phase === "idle") {
    elements.toast.hidden = true;
    elements.toast.textContent = "";
    elements.toast.removeAttribute("data-error");
    if (phase === "running") {
      elements.root.setAttribute("data-agent-active", "true");
      if (message?.trim()) {
        elements.statusLabel.textContent = message.trim();
      }
    } else {
      elements.root.setAttribute("data-agent-active", "false");
    }
    return;
  }

  if (phase === "error" && message) {
    elements.statusLabel.textContent = "Error";
    showToast(message, true);
    return;
  }

  if (phase === "complete") {
    elements.statusLabel.textContent = "Complete";
    elements.root.setAttribute("data-agent-active", "false");
    if (message) {
      showToast(message);
    }
    return;
  }

  elements.toast.removeAttribute("data-error");
}

export function applyWaitingForUser(
  elements: OverlayElements,
  message: string,
): void {
  elements.root.setAttribute("data-takeover", "true");
  elements.waitingPanel.hidden = false;
  elements.waitingMessage.textContent = message;
}

export function clearWaitingForUser(elements: OverlayElements): void {
  elements.root.setAttribute("data-takeover", "false");
  elements.waitingPanel.hidden = true;
  elements.waitingMessage.textContent = "";
}

export function applyCursorPosition(
  elements: OverlayElements,
  x: number,
  y: number,
): void {
  elements.cursor.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;
}

export function applyHighlightRect(
  elements: OverlayElements,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  elements.highlight.style.left = `${Math.round(x)}px`;
  elements.highlight.style.top = `${Math.round(y)}px`;
  elements.highlight.style.width = `${Math.max(0, Math.round(width))}px`;
  elements.highlight.style.height = `${Math.max(0, Math.round(height))}px`;
}

export function applyOverlayVisibility(
  elements: OverlayElements,
  visible: boolean,
): void {
  elements.root.setAttribute("data-visible", visible ? "true" : "false");
}