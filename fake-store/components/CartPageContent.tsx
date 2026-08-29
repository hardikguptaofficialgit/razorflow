"use client";

import Link from "next/link";
import { CartLineItem } from "@/components/CartLineItem";
import { useCart } from "@/lib/cart-context";
import { formatPrice } from "@/lib/format";
import { getProductById } from "@/lib/products";
import { demoRoutes } from "@/lib/demo-routes";

export function CartPageContent() {
  const { items, removeFromCart, updateQuantity, getCartTotal, ready } =
    useCart();
  const total = getCartTotal();

  const validItems = items
    .map((line) => {
      const product = getProductById(line.productId);
      return product ? { line, product } : null;
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  if (!ready) {
    return (
      <div className="rf-card rf-card--static px-6 py-12 text-center">
        <p className="text-sm text-[var(--rf-muted)]">Loading your cart…</p>
      </div>
    );
  }

  if (validItems.length === 0) {
    return (
      <div className="rf-card rf-card--static px-6 py-16 text-center">
        <h2 className="font-display text-xl font-semibold text-[var(--rf-ink)]">
          Your cart is empty
        </h2>
        <p className="mt-2 text-sm text-[var(--rf-muted)]">
          Browse the catalog or ask RazorFlow to shop for you.
        </p>
        <Link href={demoRoutes.search} className="rf-btn-gloss mt-6 inline-flex">
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <ul className="space-y-4">
        {validItems.map(({ line, product }) => (
          <CartLineItem
            key={line.productId}
            product={product}
            quantity={line.quantity}
            onUpdateQuantity={(quantity) =>
              updateQuantity(line.productId, quantity)
            }
            onRemove={() => removeFromCart(line.productId)}
          />
        ))}
      </ul>

      <aside className="rf-card rf-card--static h-fit p-6">
        <h2 className="font-display text-lg font-semibold text-[var(--rf-ink)]">
          Order summary
        </h2>
        <div className="mt-4 flex items-center justify-between text-sm text-[var(--rf-muted)]">
          <span>
            Subtotal ({validItems.reduce((sum, entry) => sum + entry.line.quantity, 0)} items)
          </span>
          <span className="font-medium text-[var(--rf-ink)]">
            {formatPrice(total)}
          </span>
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-[var(--rf-ink)]/10 pt-4">
          <span className="font-semibold text-[var(--rf-ink)]">Total</span>
          <span className="font-display text-xl font-semibold text-[var(--rf-ink)]">
            {formatPrice(total)}
          </span>
        </div>
        <Link
          href={demoRoutes.checkout}
          className="rf-btn-gloss rf-btn-gloss--block mt-6 text-center"
          data-rf-label="Proceed to checkout"
          data-rf-interactive
        >
          Proceed to checkout
        </Link>
        <Link
          href={demoRoutes.search}
          className="rf-btn-ghost-dark mt-3 block w-full text-center !py-3"
        >
          Continue shopping
        </Link>
      </aside>
    </div>
  );
}
