"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuthModal } from "@/lib/auth-modal-context";
import { demoRoutes } from "@/lib/demo-routes";
import { useToast } from "@/lib/toast-context";

export function StoreUrlEffects() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { openAuth } = useAuthModal();
  const { showToast } = useToast();

  useEffect(() => {
    const auth = searchParams.get("auth");
    const next = searchParams.get("next");
    const ordered = searchParams.get("ordered");

    const params = new URLSearchParams(searchParams.toString());
    let changed = false;

    if (auth === "login" || auth === "signup") {
      openAuth(auth, next?.startsWith("/") ? next : null);
      params.delete("auth");
      params.delete("next");
      changed = true;
    }

    if (ordered === "1") {
      showToast("Order placed successfully. Thank you for shopping!", "success");
      params.delete("ordered");
      changed = true;
    }

    if (changed) {
      const query = params.toString();
      const base =
        pathname.startsWith(demoRoutes.home) ? pathname.split("?")[0] : demoRoutes.home;
      router.replace(query ? `${base}?${query}` : base, { scroll: false });
    }
  }, [searchParams, openAuth, showToast, router, pathname]);

  return null;
}
