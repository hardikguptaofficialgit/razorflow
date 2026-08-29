"use client";

import Link from "next/link";
import { useCart } from "@/lib/cart-context";
import { demoRoutes } from "@/lib/demo-routes";

function CartIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0 text-gray-900"
      aria-hidden="true"
    >
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
    </svg>
  );
}

export function CartLink() {
  const { itemCount, ready } = useCart();
  const labelCount = ready ? itemCount : 0;

  return (
    <Link
      href={demoRoutes.cart}
      className="relative inline-flex items-center gap-2 rounded-lg border border-transparent px-3 py-2 text-sm font-semibold text-gray-900 hover:border-gray-200 hover:bg-gray-100"
      aria-label={`Cart, ${labelCount} items`}
      data-rf-cart-link
      data-rf-interactive
    >
      <CartIcon />
      <span className="hidden text-gray-900 sm:inline">Cart</span>
      <span
        className={
          ready && labelCount > 0
            ? "absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-gray-900 px-1 text-[11px] font-bold text-white"
            : "sr-only"
        }
        aria-hidden={!(ready && labelCount > 0)}
        data-rf-cart-count
      >
        {labelCount > 99 ? "99+" : labelCount}
      </span>
    </Link>
  );
}
