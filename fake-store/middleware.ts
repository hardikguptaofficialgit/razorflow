import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { DEMO_BASE, demoPath } from "@/lib/demo-routes";
import {
  getSupabaseAnonKey,
  getSupabaseUrl,
  isSupabaseConfigured,
} from "@/lib/supabase/config";

const LEGACY_STORE_PREFIXES = [
  "/account",
  "/cart",
  "/checkout",
  "/search",
  "/product",
  "/login",
  "/signup",
] as const;

export async function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;

  if (path === "/profile" || path.startsWith("/profile/")) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = demoPath("/account");
    return NextResponse.redirect(redirectUrl);
  }

  for (const prefix of LEGACY_STORE_PREFIXES) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = demoPath(path);
      return NextResponse.redirect(redirectUrl);
    }
  }

  let response = NextResponse.next({
    request,
  });

  if (!isSupabaseConfigured()) {
    return response;
  }

  const supabase = createServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(
        cookiesToSet: {
          name: string;
          value: string;
          options: CookieOptions;
        }[],
      ) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (
    (path.startsWith(`${DEMO_BASE}/account`) || path === `${DEMO_BASE}/checkout`) &&
    !user
  ) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = DEMO_BASE;
    redirectUrl.searchParams.set("auth", "login");
    redirectUrl.searchParams.set("next", path);
    return NextResponse.redirect(redirectUrl);
  }

  if (path === `${DEMO_BASE}/login` || path === `${DEMO_BASE}/signup`) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = DEMO_BASE;
    redirectUrl.searchParams.set(
      "auth",
      path === `${DEMO_BASE}/login` ? "login" : "signup",
    );
    const next = request.nextUrl.searchParams.get("next");
    if (next?.startsWith("/")) {
      redirectUrl.searchParams.set("next", next);
    }
    return NextResponse.redirect(redirectUrl);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|brand/|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
