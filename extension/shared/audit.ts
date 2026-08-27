export interface PaymentAuditEntry {
  runId: string;
  eventType: string;
  message: string;
  timestamp: string;
  details: Record<string, unknown>;
}

export interface PaymentAuditSnapshot {
  runId: string;
  entries: PaymentAuditEntry[];
}

export const PAYMENT_AUDIT_API_BASE = "http://127.0.0.1:8765/audit/payment";

export function formatAuditEventType(eventType: string): string {
  switch (eventType) {
    case "policy_check_started":
      return "Policy check";
    case "policy_approved":
      return "Policy approved";
    case "policy_blocked":
      return "Policy blocked";
    case "mcp_create_payment_link_called":
      return "MCP create_payment_link";
    case "payment_link_success":
      return "Payment link created";
    case "payment_link_failure":
      return "Payment link failed";
    default:
      return eventType.replaceAll("_", " ");
  }
}
