import type { TimelineEventKind } from "./run-timeline";

export interface TimelinePresentation {
  badge: string;
  title: string;
}

const PRESENTATION: Record<TimelineEventKind, TimelinePresentation> = {
  run_started: { badge: "Start", title: "Task started" },
  thinking: { badge: "Plan", title: "Planning next step" },
  acted: { badge: "Act", title: "Browser action" },
  action_failed: { badge: "Failed", title: "Action failed" },
  waiting_for_user: { badge: "Handoff", title: "Waiting for you" },
  resumed: { badge: "Resume", title: "Run resumed" },
  completed: { badge: "Done", title: "Run completed" },
  cancelled: { badge: "Stop", title: "Run cancelled" },
  error: { badge: "Error", title: "Run error" },
  payment_confirmation: {
    badge: "Confirm",
    title: "Payment confirmation requested",
  },
  policy_check: { badge: "Policy", title: "Policy check started" },
  policy_approved: { badge: "Approved", title: "Policy approved" },
  policy_blocked: { badge: "Blocked", title: "Policy blocked" },
  mcp_payment_link: { badge: "MCP", title: "Razorpay MCP called" },
  payment_link_ready: { badge: "Link", title: "Payment link ready" },
  payment_link_failed: { badge: "Failed", title: "Payment link failed" },
};

export function presentTimelineEvent(
  kind: TimelineEventKind,
  label: string,
): TimelinePresentation {
  const base = PRESENTATION[kind];
  return {
    badge: base.badge,
    title: label || base.title,
  };
}
