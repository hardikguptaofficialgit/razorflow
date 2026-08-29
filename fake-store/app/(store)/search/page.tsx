import { Suspense } from "react";
import { SearchResults } from "@/components/SearchResults";
import { PRODUCT_CATEGORIES, type ProductCategory } from "@/data/types";
import { searchProducts } from "@/lib/products";

interface SearchPageProps {
  searchParams: Promise<{ q?: string; category?: string }>;
}

function isProductCategory(value: string): value is ProductCategory {
  return PRODUCT_CATEGORIES.includes(value as ProductCategory);
}

export default async function DemoSearchPage({ searchParams }: SearchPageProps) {
  const { q = "", category } = await searchParams;
  const results = searchProducts(q);
  const initialCategory =
    category && isProductCategory(category) ? category : null;

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <Suspense
        fallback={
          <p className="text-sm text-[var(--rf-muted)]">Loading products…</p>
        }
      >
        <SearchResults
          query={q}
          initialCategory={initialCategory}
          products={results}
        />
      </Suspense>
    </main>
  );
}
