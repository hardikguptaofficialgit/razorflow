import type { AgentState, HighlightRect, OverlaySnapshot } from "../shared/types";
import { AGENT_STATE_LABELS } from "../shared/types";
import { DEFAULT_WAITING_MESSAGE } from "../shared/run-timeline";
import { animateCursorTo, flashHighlight, pulseStatus } from "./animations";
import { bindOverlayControls } from "./overlay-controls";
import {
  bindWaitingPanelActions,
  sendOverlayHandoffAction,
} from "./overlay-handoff";
import {
  bindPaymentPanelActions,
  applyPaymentConfirmation,
  applyPaymentLinkReady,
  clearPaymentHandoff,
  sendPaymentHandoffAction,
} from "./overlay-payment";
import {
  applyAgentStateToDom,
  applyCursorPosition,
  applyHighlightRect,
  applyOverlayVisibility,
  applyRunPhaseToDom,
  applyWaitingForUser,
  clearWaitingForUser,
  createOverlayRoot,
  type OverlayElements,
  type OverlayRunPhase,
} from "./overlay-dom";

const ACTIVE_STATES: AgentState[] = [
  "listening",
  "thinking",
  "acting",
  "paused",
  "waiting_for_user",
];

export class OverlayController {
  private readonly elements: OverlayElements;
  private snapshot: OverlaySnapshot = {
    visible: true,
    state: "idle",
    cursor: { x: 48, y: 48 },
  };

  constructor() {
    this.elements = createOverlayRoot();
    bindWaitingPanelActions(this.elements, (action) => {
      sendOverlayHandoffAction(action);
    });
    bindPaymentPanelActions(this.elements, (action) => {
      sendPaymentHandoffAction(action);
    });
    bindOverlayControls(this.elements);
    this.syncDom();
  }

  getElements(): OverlayElements {
    return this.elements;
  }

  setState(state: AgentState): void {
    if (state !== "waiting_for_user") {
      clearWaitingForUser(this.elements);
    }

    this.snapshot.state = state;
    applyAgentStateToDom(
      this.elements,
      state,
      AGENT_STATE_LABELS[state],
    );

    if (ACTIVE_STATES.includes(state)) {
      pulseStatus(this.elements);
    }
  }

  enterWaitingForUser(message?: string): void {
    const reason = message?.trim() || DEFAULT_WAITING_MESSAGE;
    this.snapshot.state = "waiting_for_user";
    applyAgentStateToDom(
      this.elements,
      "waiting_for_user",
      AGENT_STATE_LABELS.waiting_for_user,
    );
    applyWaitingForUser(this.elements, reason);
    pulseStatus(this.elements);
  }

  exitWaitingMode(): void {
    clearWaitingForUser(this.elements);
  }

  showPaymentConfirmation(
    proposal: import("../shared/payment-link").PaymentLinkProposal,
  ): void {
    applyPaymentConfirmation(this.elements, proposal);
    this.snapshot.state = "waiting_for_user";
    applyAgentStateToDom(
      this.elements,
      "waiting_for_user",
      AGENT_STATE_LABELS.waiting_for_user,
    );
  }

  showPaymentLinkReady(
    result: import("../shared/payment-link").PaymentLinkResult,
  ): void {
    applyPaymentLinkReady(this.elements, result);
    this.snapshot.state = "waiting_for_user";
    applyAgentStateToDom(
      this.elements,
      "waiting_for_user",
      "Payment link ready",
    );
  }

  hidePaymentHandoff(): void {
    clearPaymentHandoff(this.elements);
  }

  setRunPhase(phase: OverlayRunPhase, message?: string): void {
    applyRunPhaseToDom(this.elements, phase, message);
    if (phase === "planning") {
      this.snapshot.state = "thinking";
      applyAgentStateToDom(
        this.elements,
        "thinking",
        message ?? "Planning",
      );
      pulseStatus(this.elements);
      return;
    }
    if (phase === "error") {
      pulseStatus(this.elements);
    }
  }

  moveCursor(x: number, y: number): void {
    this.snapshot.cursor = { x, y };
    animateCursorTo(this.elements, x, y);
  }

  parkCursor(): void {
    const x = Math.max(24, Math.round(window.innerWidth / 2 - 12));
    const y = Math.max(24, Math.round(window.innerHeight - 140));
    this.moveCursor(x, y);
    this.clearHighlight();
  }

  showHighlight(rect: HighlightRect): void {
    applyHighlightRect(
      this.elements,
      rect.x,
      rect.y,
      rect.width,
      rect.height,
    );
    flashHighlight(this.elements);
  }

  clearHighlight(): void {
    applyHighlightRect(this.elements, 0, 0, 0, 0);
    this.elements.highlight.classList.remove("rf-highlight--active");
  }

  toggleOverlay(visible?: boolean): void {
    this.snapshot.visible = visible ?? !this.snapshot.visible;
    applyOverlayVisibility(this.elements, this.snapshot.visible);
  }

  private syncDom(): void {
    applyOverlayVisibility(this.elements, this.snapshot.visible);
    applyAgentStateToDom(
      this.elements,
      this.snapshot.state,
      AGENT_STATE_LABELS[this.snapshot.state],
    );
    applyCursorPosition(
      this.elements,
      this.snapshot.cursor.x,
      this.snapshot.cursor.y,
    );
  }
}
