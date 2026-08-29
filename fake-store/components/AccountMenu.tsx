"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAuthModal } from "@/lib/auth-modal-context";
import { demoRoutes } from "@/lib/demo-routes";

const NAV_LINKS = [
  { href: demoRoutes.account, label: "Profile" },
  { href: demoRoutes.accountOrders, label: "Your orders" },
] as const;

export function AccountMenu() {
  const { user, loading, configured, signOut } = useAuth();
  const { openAuth } = useAuthModal();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const btnClass =
    "inline-flex items-center justify-center px-3 py-2 text-sm font-semibold text-gray-900 hover:bg-gray-100 rounded-lg transition-colors";

  if (!configured) {
    return (
      <button type="button" onClick={() => openAuth("login")} className={btnClass}>
        Account
      </button>
    );
  }

  if (loading) {
    return <span className={`${btnClass} opacity-50`}>…</span>;
  }

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => openAuth("login")} className={btnClass}>
          Sign in
        </button>
        <button
          type="button"
          onClick={() => openAuth("signup")}
          className="inline-flex items-center justify-center rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 transition-colors"
        >
          Sign up
        </button>
      </div>
    );
  }

  const displayName =
    (user.user_metadata?.display_name as string | undefined) ??
    user.email?.split("@")[0] ??
    "Account";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`${btnClass} gap-2`}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-900 text-xs font-bold text-white">
          {displayName.charAt(0).toUpperCase()}
        </span>
        <span className="hidden max-w-[120px] truncate text-gray-900 sm:inline">
          {displayName}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-gray-700 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open ? (
        <div
          className="absolute right-0 z-50 mt-2 w-56 overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-lg"
          role="menu"
        >
          <div className="border-b border-gray-100 px-4 py-3">
            <p className="truncate text-sm font-semibold text-gray-900">{displayName}</p>
            <p className="truncate text-xs text-gray-500">{user.email}</p>
          </div>
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
              role="menuitem"
            >
              {link.label}
            </Link>
          ))}
          <button
            type="button"
            onClick={() => void signOut()}
            className="block w-full px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50"
            role="menuitem"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

interface AccountShellProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function AccountShell({ title, description, children }: AccountShellProps) {
  const pathname = usePathname();
  const { user, loading, configured } = useAuth();
  const { openAuth } = useAuthModal();

  useEffect(() => {
    if (!loading && configured && !user) {
      openAuth("login", pathname);
    }
  }, [loading, configured, user, openAuth, pathname]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-12 text-center">
        <p className="text-sm text-gray-500">Loading your account…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-12 text-center">
        <h2 className="text-lg font-semibold text-gray-900">Sign in to continue</h2>
        <p className="mt-2 text-sm text-gray-500">Your profile and orders are saved to your account.</p>
        <button
          type="button"
          onClick={() => openAuth("login", pathname)}
          className="mt-6 inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800"
        >
          Sign in
        </button>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
      <aside className="h-fit rounded-2xl border border-gray-200 bg-white p-4">
        <p className="mb-3 px-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Account
        </p>
        <nav className="space-y-1">
          {NAV_LINKS.map((link) => {
            const active =
              link.href === demoRoutes.account
                ? pathname === demoRoutes.account
                : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-gray-900 text-white"
                    : "text-gray-700 hover:bg-gray-100"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <section className="rounded-2xl border border-gray-200 bg-white p-6 sm:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
          {description ? (
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          ) : null}
        </div>
        {children}
      </section>
    </div>
  );
}
