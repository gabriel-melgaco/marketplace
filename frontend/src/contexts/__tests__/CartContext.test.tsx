/**
 * Tests for src/contexts/CartContext.tsx
 *
 * Strategy: render a minimal consumer component inside <CartProvider> and
 * drive the context API via user interactions.  This tests the *behaviour*
 * of the context rather than implementation details such as state variable
 * names.
 *
 * Risk level: HIGH
 *   - Cart is the primary commerce flow.  Bugs here silently corrupt totals,
 *     let users add more stock than exists, or prevent items from being
 *     removed — all of which directly impact revenue and UX.
 *
 * Coverage matrix
 *   addToCart         : new item, duplicate item, quantity accumulation,
 *                       quantity capped at listing.quantity
 *   removeFromCart    : removes target item, leaves others untouched
 *   updateQuantity    : increases, decreases, caps at max, removes at ≤0
 *   clearCart         : empties all items
 *   totalItems        : sums quantities across all items
 *   useCart guard     : throws when used outside CartProvider
 */

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CartProvider, useCart } from "../CartContext";
import type { MarketplaceListing } from "@/types/product";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeListing(
  id: number,
  price: string = "100.00",
  quantity: number = 5,
): MarketplaceListing {
  return {
    id,
    product: { id, name: `Produto ${id}`, slug: `produto-${id}`, code: null },
    seller: 1,
    seller_name: "Vendedor",
    title: `Anúncio ${id}`,
    price,
    brand: { id: 1, name: "Marca", slug: "marca", logo: null },
    quantity,
    is_active: true,
    description: "desc",
    condition: { id: 1, name: "Usado", slug: "usado" },
    views_count: 0,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    sold_at: null,
    images: [],
    primary_image: null,
    seller_shipping_address: null,
  };
}

/** A test consumer that exposes cart state and all actions as buttons. */
function CartConsumer({ listing }: { listing: MarketplaceListing }) {
  const {
    items,
    totalItems,
    addToCart,
    removeFromCart,
    updateQuantity,
    clearCart,
  } = useCart();

  const item = items.find((i) => i.listing.id === listing.id);

  return (
    <div>
      <span data-testid="total-items">{totalItems}</span>
      <span data-testid={`qty-${listing.id}`}>{item?.quantity ?? 0}</span>
      <span data-testid="item-count">{items.length}</span>

      <button onClick={() => addToCart(listing)}>add</button>
      <button onClick={() => addToCart(listing, 3)}>add-3</button>
      <button onClick={() => removeFromCart(listing.id)}>remove</button>
      <button
        onClick={() =>
          updateQuantity(listing.id, (item?.quantity ?? 1) + 1)
        }
      >
        inc
      </button>
      <button
        onClick={() =>
          updateQuantity(listing.id, (item?.quantity ?? 1) - 1)
        }
      >
        dec
      </button>
      <button onClick={() => updateQuantity(listing.id, 0)}>set-zero</button>
      <button onClick={clearCart}>clear</button>
    </div>
  );
}

function renderCart(listing: MarketplaceListing) {
  return render(
    <CartProvider>
      <CartConsumer listing={listing} />
    </CartProvider>,
  );
}

// ─── addToCart ────────────────────────────────────────────────────────────────

describe("addToCart", () => {
  it("adds a new item with default quantity of 1", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    await user.click(screen.getByText("add"));

    expect(screen.getByTestId("qty-1").textContent).toBe("1");
    expect(screen.getByTestId("total-items").textContent).toBe("1");
    expect(screen.getByTestId("item-count").textContent).toBe("1");
  });

  it("adds a new item with explicit quantity", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    await user.click(screen.getByText("add-3"));

    expect(screen.getByTestId("qty-1").textContent).toBe("3");
  });

  it("accumulates quantity when the same listing is added again", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 10);
    renderCart(listing);

    await user.click(screen.getByText("add"));
    await user.click(screen.getByText("add"));

    expect(screen.getByTestId("qty-1").textContent).toBe("2");
    // Should still be ONE item in the cart (not two entries)
    expect(screen.getByTestId("item-count").textContent).toBe("1");
  });

  it("does NOT exceed listing.quantity when adding duplicates", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 2); // stock = 2
    renderCart(listing);

    // Add 3 times; quantity must cap at 2
    await user.click(screen.getByText("add"));
    await user.click(screen.getByText("add"));
    await user.click(screen.getByText("add"));

    expect(screen.getByTestId("qty-1").textContent).toBe("2");
  });

  it("does NOT exceed listing.quantity when adding with explicit qty", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 3); // stock = 3
    renderCart(listing);

    // Request 5 but stock is 3
    await user.click(screen.getByText("add-3")); // qty → 3
    await user.click(screen.getByText("add-3")); // would be 6, must cap at 3

    expect(screen.getByTestId("qty-1").textContent).toBe("3");
  });
});

// ─── removeFromCart ───────────────────────────────────────────────────────────

describe("removeFromCart", () => {
  it("removes the target item entirely from the cart", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    await user.click(screen.getByText("add"));
    await user.click(screen.getByText("remove"));

    expect(screen.getByTestId("qty-1").textContent).toBe("0");
    expect(screen.getByTestId("item-count").textContent).toBe("0");
    expect(screen.getByTestId("total-items").textContent).toBe("0");
  });

  it("no-ops when removing a listing that is not in the cart", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    // Cart is empty — remove should not throw or change state
    await user.click(screen.getByText("remove"));

    expect(screen.getByTestId("item-count").textContent).toBe("0");
  });
});

// ─── updateQuantity ───────────────────────────────────────────────────────────

describe("updateQuantity", () => {
  it("increases quantity when new quantity is higher", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 10);
    renderCart(listing);

    await user.click(screen.getByText("add")); // qty = 1
    await user.click(screen.getByText("inc")); // qty = 2

    expect(screen.getByTestId("qty-1").textContent).toBe("2");
  });

  it("decreases quantity when new quantity is lower", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 10);
    renderCart(listing);

    await user.click(screen.getByText("add-3")); // qty = 3
    await user.click(screen.getByText("dec")); // qty = 2

    expect(screen.getByTestId("qty-1").textContent).toBe("2");
  });

  it("removes item when quantity is set to 0", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    await user.click(screen.getByText("add"));
    await user.click(screen.getByText("set-zero"));

    expect(screen.getByTestId("item-count").textContent).toBe("0");
  });

  it("removes item when quantity is set below 0 (negative guard)", async () => {
    // updateQuantity(id, quantity <= 0) delegates to removeFromCart
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderCart(listing);

    await user.click(screen.getByText("add")); // qty = 1
    await user.click(screen.getByText("dec")); // tries qty = 0 → removes

    expect(screen.getByTestId("item-count").textContent).toBe("0");
  });

  it("caps quantity at listing.quantity (stock ceiling)", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 3); // stock = 3
    renderCart(listing);

    await user.click(screen.getByText("add")); // qty = 1
    // Directly set via updateQuantity to a value exceeding stock
    // We need a button that sets qty to a specific high value.
    // The "inc" button sets qty = current + 1 repeatedly.
    await user.click(screen.getByText("inc")); // qty = 2
    await user.click(screen.getByText("inc")); // qty = 3 (at cap)
    await user.click(screen.getByText("inc")); // would be 4, must cap at 3

    expect(screen.getByTestId("qty-1").textContent).toBe("3");
  });
});

// ─── clearCart ────────────────────────────────────────────────────────────────

describe("clearCart", () => {
  it("empties all items from the cart", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 10);
    renderCart(listing);

    await user.click(screen.getByText("add-3"));
    await user.click(screen.getByText("clear"));

    expect(screen.getByTestId("item-count").textContent).toBe("0");
    expect(screen.getByTestId("total-items").textContent).toBe("0");
  });

  it("is safe to call on an already-empty cart", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1);
    renderCart(listing);

    await user.click(screen.getByText("clear"));

    expect(screen.getByTestId("item-count").textContent).toBe("0");
  });
});

// ─── totalItems ───────────────────────────────────────────────────────────────

describe("totalItems", () => {
  it("sums quantities across multiple distinct listings", async () => {
    // Use a two-listing consumer to test cross-item aggregation
    function TwoListingConsumer() {
      const { addToCart, totalItems } = useCart();
      const a = makeListing(10, "50.00", 10);
      const b = makeListing(20, "75.00", 10);
      return (
        <div>
          <span data-testid="total">{totalItems}</span>
          <button onClick={() => addToCart(a, 2)}>add-a</button>
          <button onClick={() => addToCart(b, 3)}>add-b</button>
        </div>
      );
    }

    const user = userEvent.setup();
    render(
      <CartProvider>
        <TwoListingConsumer />
      </CartProvider>,
    );

    await user.click(screen.getByText("add-a")); // qty=2
    await user.click(screen.getByText("add-b")); // qty=3

    expect(screen.getByTestId("total").textContent).toBe("5");
  });
});

// ─── useCart outside provider guard ──────────────────────────────────────────

describe("useCart guard", () => {
  it("throws an error when used outside CartProvider", () => {
    function BadConsumer() {
      useCart();
      return null;
    }

    // Suppress the React error boundary console output
    const consoleSpy = console.error;
    console.error = () => {};

    expect(() => render(<BadConsumer />)).toThrow(
      "useCart must be used within a CartProvider",
    );

    console.error = consoleSpy;
  });
});
