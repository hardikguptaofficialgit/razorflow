"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AccountShell } from "@/components/AccountMenu";
import { formatDate, formatOrderId } from "@/lib/account-format";
import {
  ORDER_STATUS_LABELS,
  type Order,
  type OrderStatus,
  type ShippingAddress,
} from "@/lib/account-types";
import { formatPrice } from "@/lib/format";
import { demoRoutes } from "@/lib/demo-routes";

function statusClass(status: OrderStatus): string {
  switch (status) {
    case "delivered":
      return "bg-emerald-100 text-emerald-800";
    case "shipped":
      return "bg-blue-100 text-blue-800";
    case "processing":
      return "bg-amber-100 text-amber-900";
    case "cancelled":
      return "bg-red-100 text-red-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

function formatAddress(address: ShippingAddress | null): string | null {
  if (!address?.line1) {
    return null;
  }
  const parts = [
    address.line1,
    address.line2,
    [address.city, address.state, address.postalCode].filter(Boolean).join(", "),
    address.country,
  ].filter(Boolean);
  return parts.join("\n");
}

interface OrderDetailPageContentProps {
  orderId: string;
}

export function OrderDetailPageContent({ orderId }: OrderDetailPageContentProps) {
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOrder() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/orders");
        const payload = (await res.json()) as { orders?: Order[]; error?: string };
        if (!res.ok) {
          throw new Error(payload.error || "Could not load order.");
        }
        const match = (payload.orders ?? []).find((entry) => entry.id === orderId);
        if (!cancelled) {
          if (!match) {
            setError("Order not found.");
            setOrder(null);
          } else {
            setOrder(match);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load order.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadOrder();
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (loading) {
    return (
      <AccountShell title="Order details">
        <p className="text-sm text-gray-500">Loading order…</p>
      </AccountShell>
    );
  }

  if (error || !order) {
    return (
      <AccountShell title="Order details">
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error ?? "Order not found."}
        </p>
        <Link
          href={demoRoutes.accountOrders}
          className="mt-4 inline-flex text-sm font-medium text-gray-900 underline-offset-2 hover:underline"
        >
          Back to orders
        </Link>
      </AccountShell>
    );
  }

  const addressText = formatAddress(order.shipping_address);

  return (
    <AccountShell
      title={`Order #${formatOrderId(order.id)}`}
      description={`Placed on ${formatDate(order.created_at)}`}
    >
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${statusClass(order.status)}`}
        >
          {ORDER_STATUS_LABELS[order.status]}
        </span>
        <Link
          href={demoRoutes.accountOrders}
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          ← All orders
        </Link>
      </div>

      <ul className="divide-y divide-gray-200 rounded-xl border border-gray-200">
        {order.items.map((line) => (
          <li key={`${line.productId}-${line.name}`} className="flex gap-4 p-4">
            {line.imageUrl ? (
              <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-gray-100">
                <Image
                  src={line.imageUrl}
                  alt=""
                  fill
                  sizes="80px"
                  className="object-contain p-1"
                />
              </div>
            ) : (
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-xs text-gray-500">
                Item
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium text-gray-900">{line.name}</p>
              <p className="mt-1 text-sm text-gray-500">
                Qty {line.quantity} · {formatPrice(line.unitPrice)} each
              </p>
            </div>
            <p className="font-semibold text-gray-900">{formatPrice(line.lineTotal)}</p>
          </li>
        ))}
      </ul>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <div className="rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-900">Order summary</h2>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between text-gray-600">
              <span>Subtotal</span>
              <span>{formatPrice(Number(order.subtotal))}</span>
            </div>
            <div className="flex justify-between border-t border-gray-100 pt-2 font-semibold text-gray-900">
              <span>Total</span>
              <span>{formatPrice(Number(order.total))}</span>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-900">Shipping address</h2>
          {addressText ? (
            <p className="mt-3 whitespace-pre-line text-sm text-gray-600">{addressText}</p>
          ) : (
            <p className="mt-3 text-sm text-gray-500">No shipping address saved on this order.</p>
          )}
        </div>
      </div>
    </AccountShell>
  );
}
