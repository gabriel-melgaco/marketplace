import { createContext, useContext, useState, useMemo, useEffect, type ReactNode } from "react";
import type { MarketplaceListing, MarketplaceListingDetail } from "@/types/product";

/** Accepts both the summary and detail listing shapes so callers do not need unsafe casts. */
export type CartListing = MarketplaceListing | MarketplaceListingDetail;

export interface CartItem {
  listing: CartListing;
  quantity: number;
}

interface CartContextData {
  items: CartItem[];
  totalItems: number;
  addToCart: (listing: CartListing, qty?: number) => void;
  removeFromCart: (listingId: number) => void;
  updateQuantity: (listingId: number, quantity: number) => void;
  clearCart: () => void;
}

export const CartContext = createContext<CartContextData | undefined>(undefined);

const CART_STORAGE_KEY = "cart_items";

function loadCartFromStorage(): CartItem[] {
  try {
    const stored = localStorage.getItem(CART_STORAGE_KEY);
    return stored ? (JSON.parse(stored) as CartItem[]) : [];
  } catch {
    return [];
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>(loadCartFromStorage);

  useEffect(() => {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
  }, [items]);

  const totalItems = items.reduce((sum, item) => sum + item.quantity, 0);

  function addToCart(listing: CartListing, qty = 1) {
    const clampedQty = Math.max(1, Math.min(qty, listing.quantity));
    setItems((prev) => {
      const existing = prev.find((i) => i.listing.id === listing.id);
      if (existing) {
        return prev.map((i) =>
          i.listing.id === listing.id
            ? { ...i, quantity: Math.min(i.quantity + clampedQty, i.listing.quantity) }
            : i,
        );
      }
      return [...prev, { listing, quantity: clampedQty }];
    });
  }

  function removeFromCart(listingId: number) {
    setItems((prev) => prev.filter((i) => i.listing.id !== listingId));
  }

  function updateQuantity(listingId: number, quantity: number) {
    if (quantity <= 0) {
      removeFromCart(listingId);
      return;
    }
    setItems((prev) =>
      prev.map((i) =>
        i.listing.id === listingId
          ? { ...i, quantity: Math.max(1, Math.min(quantity, i.listing.quantity)) }
          : i,
      ),
    );
  }

  function clearCart() {
    setItems([]);
  }

  const contextValue = useMemo(
    () => ({ items, totalItems, addToCart, removeFromCart, updateQuantity, clearCart }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, totalItems],
  );

  return (
    <CartContext.Provider value={contextValue}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextData {
  const context = useContext(CartContext);
  if (!context) throw new Error("useCart must be used within a CartProvider");
  return context;
}
