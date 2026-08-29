import { getProductById } from "@/lib/products";
import type { OrderLineItem } from "@/lib/account-types";

export interface ValidatedOrderItems {
  items: OrderLineItem[];
  subtotal: number;
}

export function validateOrderItems(input: unknown): ValidatedOrderItems | null {
  if (!Array.isArray(input) || input.length === 0) {
    return null;
  }

  const items: OrderLineItem[] = [];
  for (const raw of input) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const line = raw as { productId?: unknown; quantity?: unknown };
    const productId = typeof line.productId === "string" ? line.productId : "";
    const quantity = typeof line.quantity === "number" ? line.quantity : 0;
    const product = getProductById(productId);

    if (
      !product ||
      !Number.isInteger(quantity) ||
      quantity < 1 ||
      quantity > product.stock
    ) {
      return null;
    }

    items.push({
      productId: product.id,
      name: product.name,
      quantity,
      unitPrice: product.price,
      lineTotal: product.price * quantity,
      imageUrl: product.imageUrl,
    });
  }

  return {
    items,
    subtotal: items.reduce((sum, item) => sum + item.lineTotal, 0),
  };
}
