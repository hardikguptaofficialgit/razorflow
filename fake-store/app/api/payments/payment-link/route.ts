import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { validateOrderItems } from "@/lib/order-validation";

interface PaymentLinkBody {
  items?: unknown;
  idempotencyKey?: unknown;
}

interface BackendPaymentLinkResponse {
  paymentLinkUrl?: string;
  amountPaise?: number;
  currency?: string;
  description?: string;
  referenceId?: string;
  reused?: boolean;
  detail?: string;
}

function backendUrl(): string {
  return (
    process.env.AGENT_BACKEND_URL?.trim() || "http://127.0.0.1:8765"
  ).replace(/\/$/, "");
}

export async function POST(request: Request) {
  const supabase = await createClient();
  if (!supabase) {
    return NextResponse.json({ error: "Auth not configured." }, { status: 500 });
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }

  let body: PaymentLinkBody;
  try {
    body = (await request.json()) as PaymentLinkBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const validated = validateOrderItems(body.items);
  const idempotencyKey =
    typeof body.idempotencyKey === "string" ? body.idempotencyKey.trim() : "";
  if (!validated || idempotencyKey.length < 8 || idempotencyKey.length > 160) {
    return NextResponse.json(
      { error: "Invalid payment request." },
      { status: 400 },
    );
  }

  const description = validated.items
    .map((item) => `${item.name} × ${item.quantity}`)
    .join(", ");
  const scopedKey = `${user.id}:${idempotencyKey}`;
  const headers: HeadersInit = { "Content-Type": "application/json" };
  const internalToken = process.env.AGENT_BACKEND_TOKEN?.trim();
  if (internalToken) {
    headers["x-razorflow-internal-token"] = internalToken;
  }

  let response: Response;
  try {
    response = await fetch(`${backendUrl()}/api/payments/payment-link`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        runId: `web-${user.id.slice(0, 8)}-${idempotencyKey.slice(0, 16)}`,
        idempotencyKey: scopedKey,
        title: `RazorFlow order (${validated.items.length} item${
          validated.items.length === 1 ? "" : "s"
        })`,
        description,
        amountPaise: Math.round(validated.subtotal * 100),
        currency: "INR",
      }),
      signal: AbortSignal.timeout(45_000),
    });
  } catch {
    return NextResponse.json(
      { error: "Payment service is unavailable. Start the agent backend and retry." },
      { status: 503 },
    );
  }

  const payload = (await response.json().catch(() => ({}))) as BackendPaymentLinkResponse;
  if (!response.ok || !payload.paymentLinkUrl) {
    return NextResponse.json(
      { error: payload.detail || "Could not create a payment link." },
      { status: response.status >= 500 ? 502 : response.status },
    );
  }

  return NextResponse.json({
    paymentLinkUrl: payload.paymentLinkUrl,
    amountPaise: payload.amountPaise,
    currency: payload.currency,
    description: payload.description,
    referenceId: payload.referenceId,
    reused: payload.reused ?? false,
  });
}
