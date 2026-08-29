/** WebSocket wire protocol between client and agent runtime. */

import type { PageContextWire } from "./observation.js";

export type TargetRole = "search" | "input" | "button" | "link";

export type ActionStep =
  | { action: "set_state"; state: string }
  | {
      action: "type_in_element";
      role: TargetRole;
      text: string;
      elementIndex?: number;
      matchText?: string;
    }
  | {
      action: "click_element";
      role: TargetRole;
      elementIndex?: number;
      matchText?: string;
    }
  | {
      action: "highlight_element";
      role: TargetRole;
      elementIndex?: number;
      matchText?: string;
    }
  | { action: "navigate_url"; url: string }
  | {
      action: "scroll_page";
      direction?: "up" | "down" | "top" | "bottom";
      amountPx?: number;
    }
  | { action: "wait"; durationMs?: number }
  | { action: "go_back" }
  | { action: "wait_for_user" }
  | {
      action: "ready_for_payment_link";
      title: string;
      description: string;
      amountPaise: number;
      currency: string;
    };

export type ClientToServerMessage =
  | {
      type: "START_RUN";
      runId: string;
      task: string;
      url?: string;
      pageContext?: PageContextWire;
    }
  | {
      type: "ACTION_RESULT";
      runId: string;
      step: ActionStep;
      success: boolean;
      error?: string;
      verified?: boolean;
      pageContext?: PageContextWire;
    }
  | {
      type: "RESUME_RUN";
      runId: string;
      pageContext?: PageContextWire;
    }
  | { type: "CANCEL_RUN"; runId: string }
  | { type: "CONFIRM_PAYMENT_LINK"; runId: string; confirmed: boolean }
  | { type: "DECLINE_PAYMENT_LINK"; runId: string }
  | {
      type: "CONFIGURE_AGENT";
      useByok: boolean;
      provider?: string;
      apiKey?: string;
      model?: string;
      temperature?: number;
      maxAgentSteps?: number;
      shoppingSkillEnabled?: boolean;
    };

export type ServerToClientMessage =
  | { type: "EXECUTOR_MODE"; runId: string; mode: "extension_dom" | "browser_use" }
  | {
      type: "NEXT_ACTION";
      runId: string;
      steps: ActionStep[];
      turn: number;
      actionSummary?: string;
      chatMessage?: string;
      screenshotDataUrl?: string;
      runtimePhase?: string;
    }
  | { type: "RUN_COMPLETE"; runId: string; message?: string }
  | { type: "RUN_ERROR"; runId: string; message: string }
  | { type: "RUN_WAITING_FOR_USER"; runId: string; message?: string }
  | { type: "RUN_NEEDS_CLARIFICATION"; runId: string; message: string }
  | {
      type: "PAYMENT_LINK_CONFIRMATION_REQUIRED";
      runId: string;
      proposal: PaymentLinkProposal;
      message?: string;
    }
  | {
      type: "PAYMENT_LINK_READY";
      runId: string;
      paymentLinkUrl: string;
      amountPaise: number;
      currency: string;
      referenceId: string;
      description: string;
      message?: string;
    }
  | { type: "PAYMENT_LINK_FAILED"; runId: string; message: string; recoverable?: boolean }
  | {
      type: "AGENT_SYNC";
      runId: string;
      phase: string;
      actionSummary: string;
      title?: string;
      url: string;
      step: number;
      cursor?: { x: number; y: number };
      highlight?: { x: number; y: number; width: number; height: number };
    }
  | {
      type: "AGENT_CONFIG_STATUS";
      mode: "server_default" | "byok";
      useByok: boolean;
      provider?: string;
      model?: string;
      temperature?: number;
      maxAgentSteps: number;
      shoppingSkillEnabled: boolean;
      message?: string;
    };

export interface PaymentLinkProposal {
  title: string;
  description: string;
  amountPaise: number;
  currency: string;
}
