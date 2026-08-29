import { NextResponse } from "next/server";

function getSupabaseAdminConfig() {
  const url = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").trim().replace(/\/$/, "");
  const serviceKey = (process.env.SUPABASE_SERVICE_ROLE_KEY ?? "").trim();
  if (!url || !serviceKey) {
    return null;
  }
  return { url, serviceKey };
}

export async function POST(request: Request) {
  const config = getSupabaseAdminConfig();
  if (!config) {
    return NextResponse.json(
      { error: "Server auth is not configured (missing service role key)." },
      { status: 500 },
    );
  }

  let body: {
    email?: string;
    password?: string;
    displayName?: string;
  };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const email = body.email?.trim().toLowerCase() ?? "";
  const password = body.password ?? "";
  const displayName = body.displayName?.trim() || undefined;

  if (!email || !password || password.length < 6) {
    return NextResponse.json(
      { error: "Email and password (min 6 chars) are required." },
      { status: 400 },
    );
  }

  let response: Response;
  try {
    response = await fetch(`${config.url}/auth/v1/admin/users`, {
      method: "POST",
      headers: {
        apikey: config.serviceKey,
        Authorization: `Bearer ${config.serviceKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        password,
        email_confirm: true,
        user_metadata: displayName ? { display_name: displayName } : {},
      }),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Network error";
    return NextResponse.json(
      { error: `Could not reach Supabase Auth: ${message}` },
      { status: 502 },
    );
  }

  const payload = (await response.json().catch(() => ({}))) as {
    id?: string;
    email?: string;
    msg?: string;
    message?: string;
    error_code?: string;
  };

  if (!response.ok) {
    const raw = (payload.msg || payload.message || "Sign up failed.").toLowerCase();
    if (raw.includes("already") || raw.includes("registered") || payload.error_code === "email_exists") {
      return NextResponse.json(
        { error: "An account with this email already exists. Log in instead." },
        { status: 409 },
      );
    }
    return NextResponse.json(
      { error: payload.msg || payload.message || "Sign up failed." },
      { status: response.status },
    );
  }

  return NextResponse.json({
    ok: true,
    userId: payload.id ?? null,
    email: payload.email ?? email,
  });
}
