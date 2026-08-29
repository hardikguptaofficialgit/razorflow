import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import type { ShippingAddress } from "@/lib/account-types";

interface ProfileBody {
  displayName?: string;
  phone?: string;
  shippingAddress?: ShippingAddress;
}

function normalizeAddress(value: ShippingAddress | undefined): ShippingAddress | null {
  if (!value) {
    return null;
  }
  const line1 = value.line1?.trim() ?? "";
  const city = value.city?.trim() ?? "";
  const state = value.state?.trim() ?? "";
  const postalCode = value.postalCode?.trim() ?? "";
  if (!line1 || !city || !state || !postalCode) {
    return null;
  }
  return {
    line1,
    line2: value.line2?.trim() || undefined,
    city,
    state,
    postalCode,
    country: value.country?.trim() || "India",
  };
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
    .from("profiles")
    .select("*")
    .eq("id", user.id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  if (!data) {
    const { data: created, error: insertError } = await supabase
      .from("profiles")
      .insert({
        id: user.id,
        email: user.email,
        display_name:
          (user.user_metadata?.display_name as string | undefined) ??
          user.email?.split("@")[0] ??
          "Customer",
        updated_at: new Date().toISOString(),
      })
      .select("*")
      .single();

    if (insertError) {
      return NextResponse.json({ error: insertError.message }, { status: 500 });
    }
    return NextResponse.json({ profile: created });
  }

  return NextResponse.json({ profile: data });
}

export async function PATCH(request: Request) {
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

  let body: ProfileBody;
  try {
    body = (await request.json()) as ProfileBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const updates: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };

  if (body.displayName !== undefined) {
    updates.display_name = body.displayName.trim() || null;
  }
  if (body.phone !== undefined) {
    updates.phone = body.phone.trim() || null;
  }
  if (body.shippingAddress !== undefined) {
    updates.shipping_address = normalizeAddress(body.shippingAddress) ?? {};
  }

  const { data, error } = await supabase
    .from("profiles")
    .upsert({
      id: user.id,
      email: user.email,
      ...updates,
    })
    .select("*")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ profile: data });
}
