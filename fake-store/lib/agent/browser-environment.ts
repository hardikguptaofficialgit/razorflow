/**
 * BrowserEnvironment — site-agnostic browser operations for Agent Runtime V2.
 * FakeStoreEnvironment uses the same interface; store hints are optional signals only.
 */

import type { PageContext } from "@/lib/agent/bridge-protocol";
import {
  executeActionStep,
  type ActionProgressCallback,
  type StepExecutionResult,
} from "@/lib/agent/action-executor";
import type { ActionStep } from "@/lib/agent/bridge-protocol";
import { extractPageContextWithSnapshot } from "@/lib/agent/page-snapshot";
import {
  collectRankedInteractiveElements,
  findByRole,
  isElementActionable,
  isVisible,
} from "@/lib/agent/dom-targeting";

export interface BrowserEnvironment {
  observe(): Promise<PageContext>;
  click(target: ElementTargetRef): Promise<StepExecutionResult>;
  type(target: ElementTargetRef, text: string, options?: TypeOptions): Promise<StepExecutionResult>;
  scrollToward(target: ElementTargetRef): Promise<boolean>;
  navigate(url: string): Promise<StepExecutionResult>;
  wait(ms: number): Promise<void>;
}

export interface ElementTargetRef {
  elementIndex?: number;
  role?: "search" | "input" | "button" | "link";
  matchText?: string;
}

export interface TypeOptions {
  clear?: boolean;
  submit?: boolean;
}

export class DomBrowserEnvironment implements BrowserEnvironment {
  async observe(): Promise<PageContext> {
    return extractPageContextWithSnapshot();
  }

  async click(target: ElementTargetRef): Promise<StepExecutionResult> {
    const resolved = this.resolve(target);
    if (!resolved) {
      return { success: false, error: "Target not found or not actionable." };
    }
    await this.scrollToward(target);
    return executeActionStep(
      {
        action: "click_element",
        role: target.role ?? "button",
        elementIndex: target.elementIndex,
        matchText: target.matchText,
      },
      this.onProgress,
    );
  }

  async type(
    target: ElementTargetRef,
    text: string,
    _options?: TypeOptions,
  ): Promise<StepExecutionResult> {
    await this.scrollToward(target);
    return executeActionStep(
      {
        action: "type_in_element",
        role: target.role ?? "input",
        text,
        elementIndex: target.elementIndex,
        matchText: target.matchText,
      },
      this.onProgress,
    );
  }

  async scrollToward(target: ElementTargetRef): Promise<boolean> {
    const resolved = this.resolve(target);
    if (!resolved) {
      return false;
    }
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const rect = resolved.getBoundingClientRect();
      const inView =
        rect.width > 0 &&
        rect.height > 0 &&
        rect.bottom > 0 &&
        rect.right > 0 &&
        rect.top < window.innerHeight &&
        rect.left < window.innerWidth;
      if (isVisible(resolved) && inView) {
        return true;
      }
      resolved.scrollIntoView({
        block: "center",
        inline: "center",
        behavior: attempt === 0 ? "instant" : "smooth",
      });
      await new Promise((r) => setTimeout(r, 120));
    }
    return isVisible(resolved);
  }

  async navigate(url: string): Promise<StepExecutionResult> {
    return executeActionStep(
      { action: "navigate_url", url },
      this.onProgress,
    );
  }

  async wait(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
  }

  resolve(target: ElementTargetRef): HTMLElement | null {
    if (target.elementIndex != null) {
      const ranked = collectRankedInteractiveElements();
      const element = ranked[target.elementIndex - 1];
      return element && isElementActionable(element) ? element : null;
    }
    if (target.role) {
      const match = findByRole(target.role, undefined, target.matchText);
      return match?.element && isElementActionable(match.element)
        ? match.element
        : null;
    }
    return null;
  }

  private onProgress: ActionProgressCallback = () => {};
}

/** Development adapter for the fake-store embedded agent. */
export const fakeStoreEnvironment = new DomBrowserEnvironment();

export function parseElementId(elementId: string | undefined): number | undefined {
  if (!elementId) {
    return undefined;
  }
  const match = /^e(\d+)$/i.exec(elementId.trim());
  return match ? Number.parseInt(match[1], 10) : undefined;
}

export function runtimePhaseToUiPhase(
  phase: string | undefined,
): "thinking" | "acting" | "observing" | "waiting_for_user" {
  switch (phase) {
    case "planning":
      return "thinking";
    case "observing":
    case "verifying":
      return "observing";
    case "handoff":
    case "waiting":
      return "waiting_for_user";
    case "recovering":
      return "thinking";
    default:
      return "acting";
  }
}
