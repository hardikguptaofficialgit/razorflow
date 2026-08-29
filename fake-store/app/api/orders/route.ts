import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import type { OrderLineItem, ShippingAddress } from "@/lib/account-types";

interface CreateOrderBody {
  items?: OrderLineItem[];
  subtotal?: number;
  total?: number;
  shippingAddress?: ShippingAddress | null;
}

function isValidLine(item: OrderLineItem): boolean {
  return (
    typeof item.productId === "string" &&
    item.productId.length > 0 &&
    typeof item.name === "string" &&
    item.name.length > 0 &&
    typeof item.quantity === "number" &&
    item.quantity > 0 &&
    typeof item.unitPrice === "number" &&
    item.unitPrice >= 0 &&
    typeof item.lineTotal === "number" &&
    item.lineTotal >= 0
  );
}

export async function GET() {
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

  const { data, error } = await supabase
    .from("orders")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ orders: data ?? [] });
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

  let body: CreateOrderBody;
  try {
    body = (await request.json()) as CreateOrderBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const items = body.items ?? [];
  if (!Array.isArray(items) || items.length === 0 || !items.every(isValidLine)) {
    return NextResponse.json({ error: "Invalid order items." }, { status: 400 });
  }

  const subtotal = Number(body.subtotal);
  const total = Number(body.total);
  if (!Number.isFinite(subtotal) || !Number.isFinite(total) || total <= 0) {
    return NextResponse.json({ error: "Invalid order total." }, { status: 400 });
  }

  const { data, error } = await supabase
    .from("orders")
    .insert({
      user_id: user.id,
      status: "placed",
      items,
      subtotal,
      total,
      currency: "INR",
      shipping_address: body.shippingAddress ?? null,
      updated_at: new Date().toISOString(),
    })
    .select("id, created_at, status, total")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ order: data });
}
