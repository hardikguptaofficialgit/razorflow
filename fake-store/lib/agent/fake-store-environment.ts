/**
 * FakeStoreEnvironment — BrowserEnvironment for the embedded demo store.
 * Store-specific hints are optional overlays; core observation is generic.
 */

import type { BrowserEnvironment, StepResult } from "@hardik21232323/razorflow-browser";
import {
  buildBrowserObservation,
  observationToWire,
} from "@hardik21232323/razorflow-browser";
import type {
  ActionStep,
  BrowserObservation,
  EnvironmentHints,
  ListingHint,
  PageContextWire,
} from "@hardik21232323/razorflow-protocol";
import {
  executeActionStep,
  waitForStablePage,
  type ActionProgressCallback,
} from "@/lib/agent/action-executor";
import { isVisible } from "@/lib/agent/dom-targeting";
import { extractPageContextWithSnapshot } from "@/lib/agent/page-snapshot";
import type { PageContext } from "@/lib/agent/bridge-protocol";

const AGENT_UI_SELECTOR = "[data-rf-agent-root]";

function excludeAgentUi(el: Element): boolean {
  return Boolean(el.closest(AGENT_UI_SELECTOR));
}

function collectStoreHints(): EnvironmentHints | undefined {
  const listings: ListingHint[] = [];
  for (const card of document.querySelectorAll<HTMLElement>(
    "[data-rf-product-card], article.rf-card",
  )) {
    if (!isVisible(card)) {
      continue;
    }
    const title =
      card.querySelector("[data-rf-product-title], h1,h2,h3")?.textContent?.trim() ??
      "";
    if (!title) {
      continue;
    }
    const price =
      card.querySelector("[data-rf-product-price]")?.textContent?.trim() ?? "";
    listings.push({
      id: `listing-${listings.length}`,
      title: title.slice(0, 120),
      subtitle: price.slice(0, 80),
    });
    if (listings.length >= 32) {
      break;
    }
  }

  const cartLines: EnvironmentHints["cart"] = { lines: [] };
  for (const line of document.querySelectorAll<HTMLElement>("[data-rf-cart-line]")) {
    if (!isVisible(line)) {
      continue;
    }
    const title =
      line.querySelector("[data-rf-product-title], h3")?.textContent?.trim() ?? "";
    if (!title) {
      continue;
    }
    const qtyText =
      line.querySelector("[data-rf-line-qty]")?.textContent?.trim() ?? "1";
    const quantity = Number.parseInt(qtyText, 10) || 1;
    cartLines.lines.push({ title: title.slice(0, 120), quantity });
  }

  if (listings.length === 0 && cartLines.lines.length === 0) {
    return undefined;
  }
  return {
    listings: listings.length > 0 ? listings : undefined,
    cart: cartLines.lines.length > 0 ? cartLines : undefined,
  };
}

function pageContextToWire(ctx: PageContext): PageContextWire {
  return {
    title: ctx.title,
    url: ctx.url,
    elements: ctx.elements,
    products: ctx.products,
    cartLines: ctx.cartLines,
    screenshotDataUrl: ctx.screenshotDataUrl,
  };
}

export class FakeStoreEnvironment implements BrowserEnvironment {
  async observe(): Promise<BrowserObservation> {
    const hints = collectStoreHints();
    const wire = await extractPageContextWithSnapshot();
    const obs = buildBrowserObservation({
      exclude: excludeAgentUi,
      hints,
      screenshotDataUrl: wire.screenshotDataUrl,
    });
    return obs;
  }

  async observeWire(): Promise<PageContextWire> {
    const ctx = await extractPageContextWithSnapshot();
    return pageContextToWire(ctx);
  }

  async executeStep(
    step: ActionStep,
    onProgress?: ActionProgressCallback,
  ): Promise<StepResult> {
    if (
      step.action === "wait_for_user" ||
      step.action === "ready_for_payment_link"
    ) {
      return { success: true };
    }
    const result = await executeActionStep(step, onProgress ?? (() => {}));
    return {
      success: result.success,
      verified: result.verified,
      error: result.error,
    };
  }

  async waitForStable(): Promise<PageContextWire> {
    const ctx = await waitForStablePage();
    return pageContextToWire(ctx);
  }
}

export const fakeStoreEnvironment = new FakeStoreEnvironment();
