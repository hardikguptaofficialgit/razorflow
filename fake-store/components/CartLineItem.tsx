"use client";

import Image from "next/image";
import type { Product } from "@/data/types";
import { formatPrice } from "@/lib/format";

interface CartLineItemProps {
  product: Product;
  quantity: number;
  onUpdateQuantity: (quantity: number) => void;
  onRemove: () => void;
}

export function CartLineItem({
  product,
  quantity,
  onUpdateQuantity,
  onRemove,
}: CartLineItemProps) {
  const lineTotal = product.price * quantity;
  const atMin = quantity <= 1;
  const atMax = quantity >= product.stock;

  return (
    <li className="rf-card rf-card--static flex flex-col gap-4 p-4 sm:flex-row sm:items-center" data-rf-cart-line>
      <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-[rgba(236,234,243,0.7)]">
        <Image
          src={product.imageUrl}
          alt={product.name}
          fill
          sizes="96px"
          className="object-contain p-1"
        />
      </div>

      <div className="min-w-0 flex-1">
        <h3 className="font-medium text-[var(--rf-ink)]">{product.name}</h3>
        <p className="mt-1 text-sm text-[var(--rf-muted)]">
          {formatPrice(product.price)} each
        </p>
        <p className="mt-2 text-sm text-[var(--rf-muted)]">
          {product.stock} available
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 sm:flex-col sm:items-end">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onUpdateQuantity(quantity - 1)}
            disabled={atMin}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--rf-ink)]/15 text-[var(--rf-ink)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Decrease quantity"
          >
            −
          </button>
          <span className="w-8 text-center text-sm font-medium">{quantity}</span>
          <button
            type="button"
            onClick={() => onUpdateQuantity(quantity + 1)}
            disabled={atMax}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--rf-ink)]/15 text-[var(--rf-ink)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Increase quantity"
          >
            +
          </button>
        </div>

        <p className="font-display text-lg font-semibold text-[var(--rf-ink)]">
          {formatPrice(lineTotal)}
        </p>

        <button
          type="button"
          onClick={onRemove}
          data-rf-remove-item
          data-rf-label={`Remove ${product.name}`}
          className="text-sm font-medium text-[var(--rf-danger)] transition hover:opacity-80"
        >
          Remove
        </button>
      </div>
    </li>
  );
}
