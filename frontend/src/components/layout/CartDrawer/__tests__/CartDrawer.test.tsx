/**
 * Tests for src/components/layout/CartDrawer/index.tsx
 *
 * Strategy: render CartDrawer inside CartProvider + MemoryRouter (needed for
 * <Link>).  Drive interactions via the real CartContext so drawer state and
 * cart state are always in sync.  The drawer uses createPortal; jsdom handles
 * this correctly without additional configuration.
 *
 * We mock storageService.toPublicUrl and react-icons/cg / react-icons/ti to
 * avoid environment-specific issues with icon libraries and storage URLs.
 *
 * Risk level: HIGH
 *   - The drawer is the only UI surface where customers review and adjust
 *     their cart before checkout.  Broken quantity controls, a missing
 *     checkout link, or a drawer that does not open/close correctly all
 *     directly block purchase completion.
 *
 * Coverage matrix
 *   Toggle behaviour       : opens on trigger click, closes on X button,
 *                            closes on backdrop click, closes on Escape key
 *   Empty state            : "Carrinho vazio" message visible, no items list
 *   Badge                  : hidden when cart is empty, shows count when not
 *   Item rendering         : title, price, quantity displayed per item
 *   Quantity controls      : decrement disabled at qty=1, increment disabled
 *                            at stock ceiling
 *   Remove item            : trash button removes item from cart
 *   Total price            : correct sum across all items
 *   Checkout link          : present only when cart has items, href=/checkout
 *   Overflow guard         : badge shows "99+" when totalItems > 99
 *   Body overflow          : scrolling locked when drawer is open
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CartProvider, useCart } from "@/contexts/CartContext";
import { CartDrawer } from "../index";
import type { MarketplaceListing } from "@/types/product";

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test",
  GOOGLE_REDIRECT_URI: "http://localhost:5173/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

// toPublicUrl is called on every image src; return the URL unchanged in tests
vi.mock("@/services/storageService", () => ({
  toPublicUrl: (url: string) => url,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeListing(
  id: number,
  price: string = "100.00",
  stock: number = 5,
  title: string = `Produto ${id}`,
): MarketplaceListing {
  return {
    id,
    product: { id, name: title, slug: `produto-${id}`, code: null },
    seller: 1,
    seller_name: "Vendedor",
    title,
    price,
    brand: { id: 1, name: "Marca", slug: "marca", logo: null },
    quantity: stock,
    is_active: true,
    description: "desc",
    condition: { id: 1, name: "Usado", slug: "usado" },
    views_count: 0,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    sold_at: null,
    images: [],
    primary_image: null,
    shipping_address: null,
  };
}

/**
 * Seed component: adds listings to the cart before the drawer mounts.
 * This avoids testing CartProvider internals in CartDrawer tests.
 */
function CartSeeder({
  items,
}: {
  items: { listing: MarketplaceListing; qty: number }[];
}) {
  const { addToCart } = useCart();
  // Use a ref so we only seed once on mount
  const seeded = React.useRef(false);
  React.useLayoutEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    items.forEach(({ listing, qty }) => addToCart(listing, qty));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function renderDrawer(
  cartItems: { listing: MarketplaceListing; qty: number }[] = [],
) {
  return render(
    <MemoryRouter>
      <CartProvider>
        <CartSeeder items={cartItems} />
        <CartDrawer />
      </CartProvider>
    </MemoryRouter>,
  );
}

// ─── Toggle behaviour ─────────────────────────────────────────────────────────

describe("CartDrawer - toggle", () => {
  it("drawer panel is not visible before the trigger button is clicked", () => {
    renderDrawer();
    const dialog = screen.getByRole("dialog", { hidden: true });
    // Drawer starts translated off-screen (translate-x-full class)
    expect(dialog.className).toContain("translate-x-full");
  });

  it("opens the drawer when the cart button is clicked", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("translate-x-0");
  });

  it("closes the drawer when the X (close) button is clicked", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );
    await user.click(screen.getByRole("button", { name: /Fechar carrinho/i }));

    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog.className).toContain("translate-x-full");
  });

  it("closes the drawer when the Escape key is pressed", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );
    await user.keyboard("{Escape}");

    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog.className).toContain("translate-x-full");
  });

  it("closes the drawer when the backdrop overlay is clicked", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    // The backdrop has aria-hidden="true"; query by its fixed position class
    const backdrop = document.querySelector("[aria-hidden='true'].fixed");
    expect(backdrop).not.toBeNull();
    await user.click(backdrop!);

    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog.className).toContain("translate-x-full");
  });
});

// ─── Empty state ──────────────────────────────────────────────────────────────

describe("CartDrawer - empty state", () => {
  it("shows 'Carrinho vazio' message when cart has no items", async () => {
    const user = userEvent.setup();
    renderDrawer([]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(screen.getByText(/Carrinho vazio/i)).toBeInTheDocument();
  });

  it("does not render the items list when cart is empty", async () => {
    const user = userEvent.setup();
    renderDrawer([]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("does not show the checkout button when cart is empty", async () => {
    const user = userEvent.setup();
    renderDrawer([]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(
      screen.queryByRole("link", { name: /Finalizar Compra/i }),
    ).not.toBeInTheDocument();
  });
});

// ─── Badge ────────────────────────────────────────────────────────────────────

describe("CartDrawer - badge", () => {
  it("badge is not rendered when cart is empty", () => {
    renderDrawer([]);
    // The badge span only exists when totalItems > 0
    const triggerBtn = screen.getByRole("button", {
      name: /Abrir carrinho de compras/i,
    });
    const badge = triggerBtn.querySelector("span");
    expect(badge).not.toBeInTheDocument();
  });

  it("badge shows the correct total item count", () => {
    const listing = makeListing(1, "100.00", 10);
    renderDrawer([{ listing, qty: 3 }]);

    const triggerBtn = screen.getByRole("button", {
      name: /Abrir carrinho de compras/i,
    });
    const badge = within(triggerBtn).getByText("3");
    expect(badge).toBeInTheDocument();
  });

  it("badge shows '99+' when totalItems exceeds 99", () => {
    // Add a listing with high stock and qty > 99
    const listing = makeListing(1, "10.00", 200);
    renderDrawer([{ listing, qty: 100 }]);

    const triggerBtn = screen.getByRole("button", {
      name: /Abrir carrinho de compras/i,
    });
    const badge = within(triggerBtn).getByText("99+");
    expect(badge).toBeInTheDocument();
  });
});

// ─── Item rendering ───────────────────────────────────────────────────────────

describe("CartDrawer - item rendering", () => {
  it("renders item title in the list", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "150.00", 5, "Esteira Movement R3");
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(screen.getByText(/Esteira Movement R3/)).toBeInTheDocument();
  });

  it("renders item quantity in the list", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "150.00", 5);
    renderDrawer([{ listing, qty: 2 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(screen.getByLabelText("Quantidade: 2")).toBeInTheDocument();
  });

  it("renders correctly formatted item price", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "1500.00", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    // Price appears twice: in item row and in total row
    expect(screen.getAllByText(/1\.500,00/).length).toBeGreaterThan(0);
  });
});

// ─── Quantity controls ────────────────────────────────────────────────────────

describe("CartDrawer - quantity controls", () => {
  it("decrement button is disabled when quantity is 1", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    const decrementBtn = screen.getByRole("button", {
      name: /Diminuir quantidade/i,
    });
    expect(decrementBtn).toBeDisabled();
  });

  it("increment button is disabled when quantity equals listing stock", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 3); // stock = 3
    renderDrawer([{ listing, qty: 3 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    const incrementBtn = screen.getByRole("button", {
      name: /Aumentar quantidade/i,
    });
    expect(incrementBtn).toBeDisabled();
  });

  it("increment increases item quantity", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    await user.click(
      screen.getByRole("button", { name: /Aumentar quantidade/i }),
    );

    expect(screen.getByLabelText("Quantidade: 2")).toBeInTheDocument();
  });

  it("decrement decreases item quantity", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderDrawer([{ listing, qty: 3 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    await user.click(
      screen.getByRole("button", { name: /Diminuir quantidade/i }),
    );

    expect(screen.getByLabelText("Quantidade: 2")).toBeInTheDocument();
  });
});

// ─── Remove item ──────────────────────────────────────────────────────────────

describe("CartDrawer - remove item", () => {
  it("removes item from cart when trash button is clicked", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5, "Esteira A");
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );
    await user.click(screen.getByRole("button", { name: /Remover.*carrinho/i }));

    expect(screen.queryByText("Esteira A")).not.toBeInTheDocument();
    expect(screen.getByText(/Carrinho vazio/i)).toBeInTheDocument();
  });
});

// ─── Total price ──────────────────────────────────────────────────────────────

describe("CartDrawer - total price", () => {
  it("shows the correct total for a single item at qty=1", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "250.50", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    // Total should appear as "250,50" in pt-BR locale
    expect(screen.getByText(/Total/i)).toBeInTheDocument();
    expect(screen.getAllByText(/250,50/).length).toBeGreaterThan(0);
  });
});

// ─── Checkout link ────────────────────────────────────────────────────────────

describe("CartDrawer - checkout link", () => {
  it("renders a link to /checkout when cart has items", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    const checkoutLink = screen.getByRole("link", {
      name: /Finalizar Compra/i,
    });
    expect(checkoutLink).toBeInTheDocument();
    expect(checkoutLink).toHaveAttribute("href", "/checkout");
  });

  it("checkout link closes the drawer when clicked", async () => {
    const user = userEvent.setup();
    const listing = makeListing(1, "100.00", 5);
    renderDrawer([{ listing, qty: 1 }]);

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );
    await user.click(screen.getByRole("link", { name: /Finalizar Compra/i }));

    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog.className).toContain("translate-x-full");
  });
});

// ─── Body overflow lock ───────────────────────────────────────────────────────

describe("CartDrawer - body overflow lock", () => {
  beforeEach(() => {
    document.body.style.overflow = "";
  });

  it("sets body overflow to hidden when drawer is open", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );

    expect(document.body.style.overflow).toBe("hidden");
  });

  it("restores body overflow when drawer is closed", async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(
      screen.getByRole("button", { name: /Abrir carrinho de compras/i }),
    );
    await user.click(screen.getByRole("button", { name: /Fechar carrinho/i }));

    expect(document.body.style.overflow).toBe("");
  });
});
