"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAuthModal } from "@/lib/auth-modal-context";
import { useCart } from "@/lib/cart-context";
import type { ShippingAddress, UserProfile } from "@/lib/account-types";
import { formatPrice } from "@/lib/format";
import { getProductById } from "@/lib/products";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { useToast } from "@/lib/toast-context";
import { demoRoutes } from "@/lib/demo-routes";

function parseAddress(raw: unknown): ShippingAddress | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const value = raw as Record<string, string>;
  if (!value.line1?.trim()) {
    return null;
  }
  return {
    line1: value.line1,
    line2: value.line2,
    city: value.city ?? "",
    state: value.state ?? "",
    postalCode: value.postalCode ?? "",
    country: value.country ?? "India",
  };
}

export function CheckoutPageContent() {
  const router = useRouter();
  const { user, loading: authLoading, configured } = useAuth();
  const { openAuth } = useAuthModal();
  const { items, getCartTotal, clearCart, ready: cartReady } = useCart();
  const { showToast } = useToast();
  const total = getCartTotal();
  const [placing, setPlacing] = useState(false);
  const [shippingAddress, setShippingAddress] = useState<ShippingAddress | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    if (authLoading || !configured) {
      return;
    }
    if (!user) {
      openAuth("login", demoRoutes.checkout);
    }
  }, [authLoading, configured, user, openAuth]);

  useEffect(() => {
    if (!user) {
      setProfileLoading(false);
      return;
    }

    let cancelled = false;

    async function loadProfile() {
      try {
        const res = await fetch("/api/profile");
        const payload = (await res.json()) as { profile?: UserProfile };
        if (!cancelled && res.ok && payload.profile) {
          setShippingAddress(parseAddress(payload.profile.shipping_address));
        }
      } finally {
        if (!cancelled) {
          setProfileLoading(false);
        }
      }
    }

    void loadProfile();
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!cartReady || (configured && authLoading) || profileLoading) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-12 text-center">
        <p className="text-sm text-gray-500">Loading checkout…</p>
      </div>
    );
  }

  if (!configured) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-8">
        <h2 className="text-lg font-semibold text-gray-900">Auth not configured</h2>
        <p className="mt-2 text-sm text-gray-500">
          Add Supabase keys to <code>.env.local</code> and run{" "}
          <code>supabase/schema.sql</code> to enable checkout and orders.
          {!isSupabaseConfigured() ? " Keys are currently missing." : null}
        </p>
        <Link
          href={demoRoutes.home}
          className="mt-4 inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white"
        >
          Back to shop
        </Link>
      </div>
    );
  }

  if (!user) {
    return (
      <div
        className="rounded-2xl border border-gray-200 bg-white px-6 py-12 text-center"
        data-rf-auth-required
        data-rf-checkout-gate
      >
        <h2 className="text-xl font-semibold text-gray-900">Sign in to checkout</h2>
        <p className="mt-2 text-sm text-gray-500">
          Your cart is saved. Sign in to place your order.
        </p>
        <button
          type="button"
          onClick={() => openAuth("login", demoRoutes.checkout)}
          className="mt-6 inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white"
        >
          Sign in
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white px-6 py-16 text-center">
        <h2 className="text-xl font-semibold text-gray-900">Nothing to checkout</h2>
        <p className="mt-2 text-sm text-gray-500">
          Your cart is empty. Add products before checking out.
        </p>
        <Link
          href={demoRoutes.search}
          className="mt-6 inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white"
        >
          Browse products
        </Link>
      </div>
    );
  }

  async function handlePayNow() {
    setPlacing(true);
    const orderItems = items
      .map((line) => {
        const product = getProductById(line.productId);
        if (!product) {
          return null;
        }
        return {
          productId: line.productId,
          name: product.name,
          quantity: line.quantity,
          unitPrice: product.price,
          lineTotal: product.price * line.quantity,
          imageUrl: product.imageUrl,
        };
      })
      .filter((line): line is NonNullable<typeof line> => line !== null);

    if (orderItems.length === 0) {
      showToast("Your cart has no valid products.", "error");
      setPlacing(false);
      return;
    }

    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: orderItems,
          subtotal: total,
          total,
          shippingAddress,
        }),
      });
      const payload = (await res.json()) as {
        order?: { id: string };
        error?: string;
      };

      if (!res.ok || !payload.order?.id) {
        throw new Error(payload.error || "Could not place order.");
      }

      clearCart();
      showToast("Order placed successfully!", "success");
      router.push(demoRoutes.order(payload.order.id));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not place order.";
      showToast(message, "error");
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-2xl border border-gray-200 bg-white p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-gray-900">Order summary</h2>
        <p className="mt-1 text-sm text-gray-500">Signed in as {user.email}</p>

        <ul className="mt-4 divide-y divide-gray-100">
          {items.map((line) => {
            const product = getProductById(line.productId);
            if (!product) {
              return null;
            }

            return (
              <li
                key={line.productId}
                className="flex items-center justify-between py-3 text-sm"
              >
                <span className="text-gray-800">
                  {product.name}{" "}
                  <span className="text-gray-500">× {line.quantity}</span>
                </span>
                <span className="font-medium text-gray-900">
                  {formatPrice(product.price * line.quantity)}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 rounded-xl border border-gray-200 p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Shipping address</h3>
              {shippingAddress ? (
                <p className="mt-2 text-sm text-gray-600">
                  {shippingAddress.line1}
                  {shippingAddress.line2 ? `, ${shippingAddress.line2}` : ""}
                  <br />
                  {[shippingAddress.city, shippingAddress.state, shippingAddress.postalCode]
                    .filter(Boolean)
                    .join(", ")}
                  <br />
                  {shippingAddress.country}
                </p>
              ) : (
                <p className="mt-2 text-sm text-amber-700">
                  Add a shipping address on your profile for faster checkout.
                </p>
              )}
            </div>
            <Link
              href={demoRoutes.account}
              className="shrink-0 text-sm font-medium text-gray-900 underline-offset-2 hover:underline"
            >
              Edit
            </Link>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-4">
          <span className="text-lg font-semibold text-gray-900">Total</span>
          <span className="text-2xl font-bold text-gray-900" data-rf-order-total>
            {formatPrice(total)}
          </span>
        </div>

        <p className="mt-4 text-xs text-gray-500">
          Orders are saved to your account. Agent-driven payments can still go through
          RazorFlow policy + Razorpay test mode.
        </p>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={() => void handlePayNow()}
            disabled={placing}
            className="inline-flex flex-1 items-center justify-center rounded-lg bg-gray-900 px-5 py-3 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
          >
            {placing ? "Placing order…" : "Place order"}
          </button>
          <Link
            href={demoRoutes.cart}
            className="inline-flex flex-1 items-center justify-center rounded-lg border border-gray-300 px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Back to cart
          </Link>
        </div>
      </div>
    </div>
  );
}
