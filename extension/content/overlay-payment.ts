import type { OverlayElements } from "./overlay-dom";
import { formatAmount } from "../shared/payment-link";
import type { PaymentLinkProposal, PaymentLinkResult } from "../shared/payment-link";

type PaymentAction = "confirm" | "decline" | "open";

export function bindPaymentPanelActions(
  elements: OverlayElements,
  onAction: (action: PaymentAction) => void,
): void {
  elements.paymentPanel
    .querySelector<HTMLButtonElement>('[data-action="confirm-payment"]')
    ?.addEventListener("click", () => onAction("confirm"));

  elements.paymentPanel
    .querySelector<HTMLButtonElement>('[data-action="decline-payment"]')
    ?.addEventListener("click", () => onAction("decline"));

  elements.paymentReadyPanel
    .querySelector<HTMLButtonElement>('[data-action="open-payment-link"]')
    ?.addEventListener("click", () => onAction("open"));
}

export function applyPaymentConfirmation(
  elements: OverlayElements,
  proposal: PaymentLinkProposal,
): void {
  elements.paymentPanel.hidden = false;
  elements.paymentReadyPanel.hidden = true;
  elements.paymentTitle.textContent = proposal.title;
  elements.paymentDescription.textContent = proposal.description;
  elements.paymentAmount.textContent = formatAmount(
    proposal.amountPaise,
    proposal.currency,
  );
  elements.root.setAttribute("data-payment-mode", "confirm");
}

export function applyPaymentLinkReady(
  elements: OverlayElements,
  result: PaymentLinkResult,
): void {
  elements.paymentPanel.hidden = true;
  elements.paymentReadyPanel.hidden = false;
  elements.paymentReadyDescription.textContent = result.description;
  elements.paymentReadyAmount.textContent = formatAmount(
    result.amountPaise,
    result.currency,
  );
  elements.paymentReadyReference.textContent = result.referenceId;
  elements.root.setAttribute("data-payment-mode", "ready");
  elements.root.dataset.paymentUrl = result.paymentLinkUrl;
}

export function clearPaymentHandoff(elements: OverlayElements): void {
  elements.paymentPanel.hidden = true;
  elements.paymentReadyPanel.hidden = true;
  elements.root.setAttribute("data-payment-mode", "none");
  delete elements.root.dataset.paymentUrl;
}

export function sendPaymentHandoffAction(action: PaymentAction): void {
  const type =
    action === "confirm"
      ? "OVERLAY_PAYMENT_CONFIRM"
      : action === "decline"
        ? "OVERLAY_PAYMENT_DECLINE"
        : "OVERLAY_PAYMENT_OPEN";

  void chrome.runtime.sendMessage({ type });
}
