"use client";

import Image from "next/image";
import Link from "next/link";
import type { Product } from "@/data/types";
import { useCart } from "@/lib/cart-context";
import { formatPrice } from "@/lib/format";
import { CATEGORY_LABELS } from "@/data/types";
import { demoRoutes } from "@/lib/demo-routes";

interface ProductCardProps {
  product: Product;
}

function StockBadge({ stock }: { stock: number }) {
  if (stock === 0) {
    return (
      <span className="rf-badge bg-red-100 text-red-700" data-rf-product-stock>
        Out of stock
      </span>
    );
  }
  if (stock < 10) {
    return (
      <span className="rf-badge bg-amber-100 text-amber-900" data-rf-product-stock>
        Only {stock} left
      </span>
    );
  }
  return (
    <span className="rf-badge bg-emerald-100 text-emerald-800" data-rf-product-stock>
      In stock
    </span>
  );
}

export function ProductCard({ product }: ProductCardProps) {
  const { items, addToCart } = useCart();
  const cartQuantity =
    items.find((line) => line.productId === product.id)?.quantity ?? 0;
  const outOfStock = product.stock === 0;
  const atStockLimit = cartQuantity >= product.stock;

  return (
    <article
      className="rf-card rf-card--static flex h-full flex-col overflow-hidden"
      data-rf-product-card
    >
      <Link
        href={demoRoutes.product(product.id)}
        className="relative aspect-square bg-[rgba(236,234,243,0.65)]"
      >
        <Image
          src={product.imageUrl}
          alt={product.name}
          fill
          sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
          className="object-contain p-4"
        />
      </Link>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--rf-muted)]">
              {CATEGORY_LABELS[product.category]}
            </p>
            <Link href={demoRoutes.product(product.id)}>
              <h2
                className="mt-1 line-clamp-2 text-sm font-semibold leading-snug text-[var(--rf-ink)] hover:underline"
                data-rf-product-title
              >
                {product.name}
              </h2>
            </Link>
          </div>
          <StockBadge stock={product.stock} />
        </div>

        <p className="line-clamp-2 text-xs text-[var(--rf-muted)]">
          {product.description}
        </p>

        <div className="mt-auto space-y-3 pt-2">
          <p
            className="font-display text-xl font-semibold text-[var(--rf-ink)]"
            data-rf-product-price
          >
            {formatPrice(product.price)}
          </p>

          <button
            type="button"
            onClick={() => addToCart(product.id)}
            disabled={outOfStock || atStockLimit}
            className="rf-btn-gloss rf-btn-gloss--block"
            data-rf-add-to-cart
            data-rf-label="Add to cart"
          >
            {outOfStock
              ? "Unavailable"
              : atStockLimit
                ? "Max in cart"
                : "Add to cart"}
          </button>
        </div>
      </div>
    </article>
  );
}
