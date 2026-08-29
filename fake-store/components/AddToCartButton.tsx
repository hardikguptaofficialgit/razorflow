"use client";

import { useCart } from "@/lib/cart-context";

interface AddToCartButtonProps {
  productId: string;
  stock: number;
}

export function AddToCartButton({ productId, stock }: AddToCartButtonProps) {
  const { items, addToCart } = useCart();
  const cartQuantity =
    items.find((line) => line.productId === productId)?.quantity ?? 0;
  const outOfStock = stock === 0;
  const atStockLimit = cartQuantity >= stock;

  return (
    <div className="space-y-3">
      {cartQuantity > 0 ? (
        <p className="text-sm font-medium text-[var(--rf-muted)]">
          {cartQuantity} in your cart
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => addToCart(productId)}
        disabled={outOfStock || atStockLimit}
        className="rf-btn-gloss rf-btn-gloss--block max-w-sm !py-3.5"
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
  );
}
