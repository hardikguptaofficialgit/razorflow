/** Demo store path helpers — all storefront routes live under /demo. */

export const DEMO_BASE = "/demo";

export const demoRoutes = {
  home: DEMO_BASE,
  search: `${DEMO_BASE}/search`,
  cart: `${DEMO_BASE}/cart`,
  checkout: `${DEMO_BASE}/checkout`,
  login: `${DEMO_BASE}/login`,
  signup: `${DEMO_BASE}/signup`,
  account: `${DEMO_BASE}/account`,
  accountOrders: `${DEMO_BASE}/account/orders`,
  product: (id: string) => `${DEMO_BASE}/product/${id}`,
  order: (id: string) => `${DEMO_BASE}/account/orders/${id}`,
  searchQuery: (query: string) =>
    `${DEMO_BASE}/search?q=${encodeURIComponent(query)}`,
  searchCategory: (category: string) =>
    `${DEMO_BASE}/search?category=${encodeURIComponent(category)}`,
} as const;

export function isDemoPath(pathname: string): boolean {
  return pathname === DEMO_BASE || pathname.startsWith(`${DEMO_BASE}/`);
}

/** Prefix a store-relative path with /demo. */
export function demoPath(path: string): string {
  if (path.startsWith(DEMO_BASE)) {
    return path;
  }
  if (path === "/") {
    return DEMO_BASE;
  }
  return `${DEMO_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
