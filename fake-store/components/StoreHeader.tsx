"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { CATEGORY_LABELS, PRODUCT_CATEGORIES, type ProductCategory } from "@/data/types";
import { AccountMenu } from "@/components/AccountMenu";
import { AuthModal } from "@/components/AuthModal";
import { CartLink } from "@/components/CartLink";
import { SearchBar } from "@/components/SearchBar";
import { StoreLogoLockup } from "@/components/StoreLogo";
import { StoreUrlEffects } from "@/components/StoreUrlEffects";
import { ToastViewport } from "@/components/ToastViewport";
import { demoRoutes } from "@/lib/demo-routes";

function CategoryNav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeCategory = searchParams.get("category");

  function linkClass(category: ProductCategory | "all"): string {
    const isActive =
      pathname === demoRoutes.search &&
      (category === "all" ? !activeCategory : activeCategory === category);
    return isActive
      ? "text-sm font-semibold text-gray-900 underline underline-offset-4"
      : "text-sm font-medium text-gray-700 hover:text-gray-900";
  }

  return (
    <nav className="flex flex-wrap items-center gap-x-5 gap-y-2" aria-label="Categories">
      <Link href={demoRoutes.search} className={linkClass("all")}>
        All
      </Link>
      {PRODUCT_CATEGORIES.map((category) => (
        <Link
          key={category}
          href={demoRoutes.searchCategory(category)}
          className={linkClass(category)}
        >
          {CATEGORY_LABELS[category]}
        </Link>
      ))}
    </nav>
  );
}

function CategoryNavFallback() {
  return (
    <nav className="flex gap-5" aria-label="Categories">
      <span className="text-sm text-gray-500">Loading…</span>
    </nav>
  );
}

function StoreHeaderContent() {
  return (
    <>
      <StoreUrlEffects />
      <ToastViewport />
      <AuthModal />

      <header className="sticky top-0 z-40 border-b border-gray-200 bg-white text-gray-900 shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:gap-6">
          <Link
            href={demoRoutes.home}
            className="shrink-0 text-2xl font-black tracking-tight text-gray-900 hover:text-gray-700"
          >
            RazorFlow
          </Link>

          <div className="hidden min-w-0 flex-1 lg:block">
            <SearchBar />
          </div>

          <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
            <AccountMenu />
            <CartLink />
          </div>
        </div>

        <div className="hidden border-t border-gray-200 bg-gray-50 lg:block">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2.5 sm:px-6">
            <Suspense fallback={<CategoryNavFallback />}>
              <CategoryNav />
            </Suspense>
            <p className="text-sm font-medium text-gray-600">
              Free demo shipping on all orders
            </p>
          </div>
        </div>

        <div className="border-t border-gray-200 bg-white px-4 py-3 lg:hidden sm:px-6">
          <SearchBar />
        </div>
      </header>
    </>
  );
}

function HeaderFallback() {
  return (
    <header className="sticky top-0 z-40 border-b border-gray-200 bg-white shadow-sm">
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
        <p className="text-2xl font-black tracking-tight text-gray-900">RazorFlow</p>
      </div>
    </header>
  );
}

export function StoreHeader() {
  return (
    <Suspense fallback={<HeaderFallback />}>
      <StoreHeaderContent />
    </Suspense>
  );
}
