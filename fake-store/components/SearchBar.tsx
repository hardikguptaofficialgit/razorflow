"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { extractSearchQuery } from "@/lib/search-query";
import { demoRoutes } from "@/lib/demo-routes";

export function SearchBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      const normalized = extractSearchQuery(trimmed) || trimmed;
      router.push(demoRoutes.searchQuery(normalized));
      return;
    }
    router.push(demoRoutes.search);
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl lg:flex-1">
      <div className="rf-search-shell rf-search-shell--light">
        <input
          type="search"
          name="q"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search products…"
          aria-label="Search products"
          data-rf-search-input
        />
        <button type="submit" className="rf-search-submit" data-rf-label="Search">
          Search
        </button>
      </div>
    </form>
  );
}
