/**
 * BrowserEnvironment — site-agnostic browser operations.
 * Implementations: embedded DOM (fake-store), Chrome extension, Playwright, etc.
 */

import type {
  ActionStep,
  BrowserObservation,
  PageContextWire,
} from "@strykerinside/razorflow-protocol";

export interface StepResult {
  success: boolean;
  verified?: boolean;
  error?: string;
}

export interface BrowserEnvironment {
  /** Capture current page state for the agent runtime. */
  observe(): Promise<BrowserObservation>;

  /** Wire format for transport (backward compatible). */
  observeWire(): Promise<PageContextWire>;

  /** Execute a server-dispatched action step. */
  executeStep(
    step: ActionStep,
    onProgress?: (summary: string) => void,
  ): Promise<StepResult>;

  /** Wait for DOM/network stability after an action. */
  waitForStable?(): Promise<PageContextWire>;

  navigate?(url: string): Promise<StepResult>;
}

export interface BrowserEnvironmentFactory {
  create(): BrowserEnvironment;
}
