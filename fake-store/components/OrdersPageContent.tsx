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

export function OrdersPageContent() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOrders() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/orders");
        const payload = (await res.json()) as { orders?: Order[]; error?: string };
        if (!res.ok) {
          throw new Error(payload.error || "Could not load orders.");
        }
        if (!cancelled) {
          setOrders(payload.orders ?? []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load orders.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadOrders();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <AccountShell title="Your orders" description="Track purchases from RazorFlow Market.">
        <p className="text-sm text-gray-500">Loading orders…</p>
      </AccountShell>
    );
  }

  if (error) {
    return (
      <AccountShell title="Your orders" description="Track purchases from RazorFlow Market.">
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      </AccountShell>
    );
  }

  if (orders.length === 0) {
    return (
      <AccountShell title="Your orders" description="Track purchases from RazorFlow Market.">
        <div className="py-8 text-center">
          <p className="text-gray-900 font-medium">No orders yet</p>
          <p className="mt-2 text-sm text-gray-500">
            When you place an order, it will show up here.
          </p>
          <Link
            href={demoRoutes.search}
            className="mt-6 inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800"
          >
            Start shopping
          </Link>
        </div>
      </AccountShell>
    );
  }

  return (
    <AccountShell title="Your orders" description="Track purchases from RazorFlow Market.">
      <ul className="divide-y divide-gray-200">
        {orders.map((order) => {
          const itemCount = order.items.reduce((sum, line) => sum + line.quantity, 0);
          const preview = order.items[0];
          return (
            <li key={order.id} className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center">
              {preview?.imageUrl ? (
                <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-gray-100">
                  <Image
                    src={preview.imageUrl}
                    alt=""
                    fill
                    sizes="64px"
                    className="object-contain p-1"
                  />
                </div>
              ) : (
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-xs font-semibold text-gray-500">
                  {itemCount} items
                </div>
              )}

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-gray-900">
                    Order #{formatOrderId(order.id)}
                  </p>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusClass(order.status)}`}
                  >
                    {ORDER_STATUS_LABELS[order.status]}
                  </span>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  {formatDate(order.created_at)} · {itemCount} item{itemCount === 1 ? "" : "s"}
                </p>
                {preview ? (
                  <p className="mt-1 truncate text-sm text-gray-700">
                    {preview.name}
                    {order.items.length > 1 ? ` +${order.items.length - 1} more` : ""}
                  </p>
                ) : null}
              </div>

              <div className="flex items-center gap-4 sm:flex-col sm:items-end">
                <p className="font-semibold text-gray-900">{formatPrice(Number(order.total))}</p>
                <Link
                  href={demoRoutes.order(order.id)}
                  className="text-sm font-medium text-gray-900 underline-offset-2 hover:underline"
                >
                  View details
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </AccountShell>
  );
}
