import { ProductGrid } from "@/components/ProductGrid";
import { getProducts } from "@/lib/products";

export default function DemoHomePage() {
  const products = getProducts();

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="mb-8 max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--rf-muted)]">
          RazorFlow Market
        </p>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-[var(--rf-ink)] sm:text-4xl">
          Shop with an agent by your side
        </h1>
        <p className="mt-2 text-[var(--rf-muted)]">
          Browse the catalog yourself, or open the RazorFlow chat to search,
          compare, and check out.
        </p>
      </div>
      <ProductGrid products={products} />
    </main>
  );
}
