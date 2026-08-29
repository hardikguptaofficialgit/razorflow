import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import type { ShippingAddress } from "@/lib/account-types";
import { validateOrderItems } from "@/lib/order-validation";

interface CreateOrderBody {
  items?: unknown;
  shippingAddress?: ShippingAddress | null;
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

  const validated = validateOrderItems(body.items);
  if (!validated) {
    return NextResponse.json({ error: "Invalid order items." }, { status: 400 });
  }

  const { items, subtotal } = validated;
  const total = subtotal;

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
