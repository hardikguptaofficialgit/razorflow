"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/lib/auth-context";
import { createClient } from "@/lib/supabase/client";
import { getProductById } from "@/lib/products";
import { useToast } from "@/lib/toast-context";

export interface CartLine {
  productId: string;
  quantity: number;
}

export type AddToCartResult =
  | "added"
  | "updated"
  | "max_stock"
  | "out_of_stock"
  | "invalid";

interface CartContextValue {
  items: CartLine[];
  itemCount: number;
  ready: boolean;
  addToCart: (productId: string) => AddToCartResult;
  removeFromCart: (productId: string) => void;
  updateQuantity: (productId: string, quantity: number) => void;
  getCartTotal: () => number;
  clearCart: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);
const GUEST_CART_KEY = "rf-market-cart";

function loadGuestCart(): CartLine[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(GUEST_CART_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as CartLine[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveGuestCart(items: CartLine[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(GUEST_CART_KEY, JSON.stringify(items));
}

export function CartProvider({ children }: { children: ReactNode }) {
  const { user, configured } = useAuth();
  const { showToast } = useToast();
  const [items, setItems] = useState<CartLine[]>([]);
  const [ready, setReady] = useState(false);
  const skipNextPersist = useRef(false);

  useEffect(() => {
    setItems(loadGuestCart().filter((line) => getProductById(line.productId)));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!configured || !user) {
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      return;
    }

    let cancelled = false;

    async function hydrateFromServer() {
      const { data } = await supabase!
        .from("carts")
        .select("items")
        .eq("user_id", user!.id)
        .maybeSingle();

      if (cancelled) {
        return;
      }

      const remote = (data?.items as CartLine[] | undefined) ?? [];
      const guest = loadGuestCart();
      const merged = mergeCarts(guest, remote);
      skipNextPersist.current = true;
      setItems(merged);
      saveGuestCart([]);
      await supabase!.from("carts").upsert({
        user_id: user!.id,
        items: merged,
        updated_at: new Date().toISOString(),
      });
    }

    void hydrateFromServer();
    return () => {
      cancelled = true;
    };
  }, [configured, user]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    if (skipNextPersist.current) {
      skipNextPersist.current = false;
      return;
    }

    if (!user) {
      saveGuestCart(items);
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      saveGuestCart(items);
      return;
    }

    const handle = window.setTimeout(() => {
      void supabase.from("carts").upsert({
        user_id: user.id,
        items,
        updated_at: new Date().toISOString(),
      });
    }, 400);

    return () => window.clearTimeout(handle);
  }, [items, user, ready]);

  const addToCart = useCallback(
    (productId: string): AddToCartResult => {
      const product = getProductById(productId);
      if (!product) {
        showToast("Product not found.", "error");
        return "invalid";
      }
      if (product.stock === 0) {
        showToast(`${product.name} is out of stock.`, "error");
        return "out_of_stock";
      }

      const existing = items.find((line) => line.productId === productId);
      let result: AddToCartResult;

      if (existing) {
        const nextQuantity = Math.min(existing.quantity + 1, product.stock);
        if (nextQuantity === existing.quantity) {
          showToast(
            `Maximum available quantity of ${product.name} is in your cart.`,
            "info",
          );
          return "max_stock";
        }
        result = "updated";
        setItems((current) =>
          current.map((line) =>
            line.productId === productId
              ? { ...line, quantity: nextQuantity }
              : line,
          ),
        );
        showToast(`Updated ${product.name} quantity in cart`, "success");
        return result;
      }

      setItems((current) => [...current, { productId, quantity: 1 }]);
      showToast(`Added ${product.name} to cart`, "success");
      return "added";
    },
    [items, showToast],
  );

  const removeFromCart = useCallback(
    (productId: string) => {
      const product = getProductById(productId);
      setItems((current) =>
        current.filter((line) => line.productId !== productId),
      );
      if (product) {
        showToast(`Removed ${product.name} from cart`, "info");
      }
    },
    [showToast],
  );

  const updateQuantity = useCallback(
    (productId: string, quantity: number) => {
      const product = getProductById(productId);
      if (!product) {
        return;
      }
      if (quantity <= 0) {
        removeFromCart(productId);
        return;
      }
      const cappedQuantity = Math.min(quantity, product.stock);
      setItems((current) =>
        current.map((line) =>
          line.productId === productId
            ? { ...line, quantity: cappedQuantity }
            : line,
        ),
      );
    },
    [removeFromCart],
  );

  const clearCart = useCallback(() => setItems([]), []);

  const getCartTotal = useCallback(() => {
    return items.reduce((sum, line) => {
      const product = getProductById(line.productId);
      return sum + (product?.price ?? 0) * line.quantity;
    }, 0);
  }, [items]);

  const itemCount = useMemo(
    () => items.reduce((sum, line) => sum + line.quantity, 0),
    [items],
  );

  const value = useMemo(
    () => ({
      items,
      itemCount,
      ready,
      addToCart,
      removeFromCart,
      updateQuantity,
      getCartTotal,
      clearCart,
    }),
    [
      items,
      itemCount,
      ready,
      addToCart,
      removeFromCart,
      updateQuantity,
      getCartTotal,
      clearCart,
    ],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

function mergeCarts(guest: CartLine[], remote: CartLine[]): CartLine[] {
  const map = new Map<string, number>();
  for (const line of [...remote, ...guest]) {
    const product = getProductById(line.productId);
    if (!product) {
      continue;
    }
    const prev = map.get(line.productId) ?? 0;
    map.set(
      line.productId,
      Math.min(prev + line.quantity, product.stock),
    );
  }
  return [...map.entries()].map(([productId, quantity]) => ({
    productId,
    quantity,
  }));
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) {
    throw new Error("useCart must be used within CartProvider");
  }
  return ctx;
}
