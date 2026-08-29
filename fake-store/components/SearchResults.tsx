"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { Product, ProductCategory } from "@/data/types";
import { CATEGORY_LABELS, PRODUCT_CATEGORIES } from "@/data/types";
import { ProductGrid } from "@/components/ProductGrid";

export type SortOption = "default" | "price-asc" | "price-desc";

interface SearchResultsProps {
  query: string;
  initialCategory?: ProductCategory | null;
  products: Product[];
}

function sortProducts(products: Product[], sort: SortOption): Product[] {
  if (sort === "default") {
    return products;
  }

  return [...products].sort((a, b) =>
    sort === "price-asc" ? a.price - b.price : b.price - a.price,
  );
}

function isProductCategory(value: string): value is ProductCategory {
  return PRODUCT_CATEGORIES.includes(value as ProductCategory);
}

export function SearchResults({
  query,
  initialCategory = null,
  products,
}: SearchResultsProps) {
  const searchParams = useSearchParams();
  const categoryParam = searchParams.get("category");
  const activeCategory: ProductCategory | "all" =
    categoryParam && isProductCategory(categoryParam)
      ? categoryParam
      : initialCategory ?? "all";

  const [sort, setSort] = useState<SortOption>("default");

  const filteredProducts = useMemo(() => {
    const byCategory =
      activeCategory === "all"
        ? products
        : products.filter((product) => product.category === activeCategory);

    return sortProducts(byCategory, sort);
  }, [products, activeCategory, sort]);

  const heading = query.trim()
    ? `Results for “${query.trim()}”`
    : activeCategory !== "all"
      ? CATEGORY_LABELS[activeCategory]
      : "All products";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-[var(--rf-ink)] sm:text-3xl">
            {heading}
          </h2>
          <p className="mt-1 text-sm text-[var(--rf-muted)]">
            {filteredProducts.length} of {products.length} shown
          </p>
        </div>

        <label className="flex shrink-0 items-center gap-2 text-sm text-[var(--rf-ink)]">
          <span className="font-medium">Sort</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as SortOption)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          >
            <option value="default">Relevance</option>
            <option value="price-asc">Price: Low to High</option>
            <option value="price-desc">Price: High to Low</option>
          </select>
        </label>
      </div>

      <ProductGrid
        products={filteredProducts}
        emptyMessage={
          query.trim()
            ? `No products match “${query.trim()}”.`
            : "No products in this category."
        }
      />
    </div>
  );
}
