export type { PaymentLinkProposal } from "@hardik21232323/razorflow-protocol";

export interface PaymentLinkResult {
  paymentLinkUrl: string;
  amountPaise: number;
  currency: string;
  description: string;
  referenceId: string;
}

export function formatAmount(amountPaise: number, currency: string): string {
  if (currency === "INR") {
    return `₹${(amountPaise / 100).toFixed(2)}`;
  }

  return `${(amountPaise / 100).toFixed(2)} ${currency}`;
}
