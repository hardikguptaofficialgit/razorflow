import { ProductCard } from "@/components/ProductCard";
import type { Product } from "@/data/types";

interface ProductGridProps {
  products: Product[];
  emptyMessage?: string;
}

export function ProductGrid({
  products,
  emptyMessage = "No products match your search.",
}: ProductGridProps) {
  if (products.length === 0) {
    return (
      <p className="rf-card rf-card--static px-6 py-12 text-center text-sm text-[var(--rf-muted)]">
        {emptyMessage}
      </p>
    );
  }

  return (
    <div
      className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      data-rf-product-grid
    >
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}
