/**
 * Tests for src/components/layout/Header/index.tsx
 *
 * Strategy: render Header inside a MemoryRouter (needed for <Link>) with a
 * controlled initial URL entry so we can assert active-link styling.  The
 * component depends on three external concerns that we stub at the module
 * level:
 *
 *   1. productService.getFilterOptions  — the only network call the component
 *      makes; we control its resolved value per-test via mockResolvedValueOnce
 *      / mockRejectedValueOnce set BEFORE render.
 *   2. AuthContext.useAuth              — we only need `isAuthenticated`; a
 *      lightweight stub avoids pulling in the full auth stack.
 *   3. Heavy layout children (Sidebar, CartDrawer) — their own test suites
 *      cover them; stubbing keeps this suite focused and fast.
 *   4. The logo asset (PNG import)      — Vite transforms these at build time;
 *      jsdom can't load binary assets, so we replace the import with a string.
 *
 * Risk level: HIGH
 *   - The category bar is the primary discovery surface.  If getFilterOptions
 *     is not called, or if the data is wired incorrectly, users see no
 *     categories and cannot browse by type.
 *   - The active-link logic drives navigation feedback.  A wrong condition
 *     causes the wrong (or no) category to appear highlighted.
 *
 * Coverage matrix
 *   Service call    : getFilterOptions called exactly once on mount
 *   Category bar    : rendered with one <Link> per returned category
 *   Empty state     : category bar absent when API returns []
 *   Error state     : error logged, category bar absent, no crash
 *   Active link     : correct link gets active class on /products?category=<slug>
 *   Inactive link   : active class absent on unrelated path
 *   Inactive link   : active class absent on /products with different category
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// ── Module mocks (must be hoisted above all other imports) ────────────────────

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test",
  GOOGLE_REDIRECT_URI: "http://localhost:5173/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

vi.mock("@/api/axios", () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

// Stub the logo PNG — jsdom cannot process binary Vite asset imports.
vi.mock("@/assets/logo1.png", () => ({ default: "logo1.png" }));

// Stub heavy layout children — their own test suites cover them in isolation.
vi.mock("@/components/layout/Sidebar", () => ({
  Sidebar: () => <div data-testid="sidebar-stub" />,
}));

vi.mock("@/components/layout/CartDrawer", () => ({
  CartDrawer: () => <div data-testid="cart-drawer-stub" />,
}));

// Stub productService so we control getFilterOptions per-test.
// vi.hoisted ensures the variable is initialised before vi.mock's hoisted factory runs.
const mockGetFilterOptions = vi.hoisted(() => vi.fn());
vi.mock("@/services/productService", () => ({
  productService: {
    getFilterOptions: mockGetFilterOptions,
  },
}));

// Default: unauthenticated user — avoids CartDrawer / Sidebar rendering paths
// that pull in contexts we haven't provided.
const mockUseAuth = vi.fn();
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

// ── Import component under test (after all vi.mock calls) ─────────────────────

import Header from "../index";

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Minimal FilterOptionsResponse shape with only the fields the component uses.
 */
function makeFilterOptions(
  categories: { id: number; name: string; slug: string }[],
) {
  return {
    categories,
    brands: [],
    conditions: [],
    price_range: { min: 0, max: 9999 },
  };
}

/**
 * Renders <Header> inside a <MemoryRouter> initialised to the given path+search.
 * Defaults to unauthenticated.
 */
function renderHeader(initialEntry: string = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Header />
    </MemoryRouter>,
  );
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Default: unauthenticated so no CartDrawer/Sidebar context is needed.
  mockUseAuth.mockReturnValue({ isAuthenticated: false });
});

// ── Service call ──────────────────────────────────────────────────────────────

describe("Header - service call", () => {
  it("calls getFilterOptions exactly once on mount", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));

    renderHeader();

    await waitFor(() => {
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1);
    });
  });

  it("does not call getFilterOptions more than once (no repeated fetches)", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));

    renderHeader();

    // Wait for the effect to complete then verify it ran exactly once.
    await waitFor(() => expect(mockGetFilterOptions).toHaveBeenCalledTimes(1));
    expect(mockGetFilterOptions).toHaveBeenCalledTimes(1);
  });
});

// ── Category bar — happy path ─────────────────────────────────────────────────

describe("Header - category bar with results", () => {
  const categories = [
    { id: 1, name: "Esteiras", slug: "esteiras" },
    { id: 2, name: "Bicicletas", slug: "bicicletas" },
    { id: 3, name: "Halteres", slug: "halteres" },
  ];

  it("renders one link per category returned by getFilterOptions", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader();

    for (const cat of categories) {
      await waitFor(() =>
        expect(screen.getByRole("link", { name: cat.name })).toBeInTheDocument(),
      );
    }
  });

  it("each category link points to /products?category=<slug>", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader();

    for (const cat of categories) {
      const link = await screen.findByRole("link", { name: cat.name });
      expect(link).toHaveAttribute("href", `/products?category=${cat.slug}`);
    }
  });

  it("renders exactly as many category links as categories returned", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader();

    // Wait for any one category to appear, then count all three.
    await screen.findByRole("link", { name: "Esteiras" });

    const allLinks = screen
      .getAllByRole("link")
      .filter((link) =>
        (link.getAttribute("href") ?? "").startsWith("/products?category="),
      );
    expect(allLinks).toHaveLength(3);
  });
});

// ── Category bar — empty state ────────────────────────────────────────────────

describe("Header - category bar empty state", () => {
  it("does not render any category links when API returns empty array", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));

    renderHeader();

    // Give the effect time to resolve before asserting absence.
    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    const categoryLinks = screen
      .getAllByRole("link")
      .filter((link) =>
        (link.getAttribute("href") ?? "").startsWith("/products?category="),
      );
    expect(categoryLinks).toHaveLength(0);
  });

  it("category bar container is not in the DOM when categories is empty", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));

    renderHeader();

    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    // The bar wraps links inside a border-t div; it is conditionally rendered
    // only when categories.length > 0.
    const bar = document.querySelector(".border-t.border-white");
    expect(bar).not.toBeInTheDocument();
  });
});

// ── Category bar — error state ────────────────────────────────────────────────

describe("Header - category bar error state", () => {
  it("logs the error when getFilterOptions throws", async () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const serviceError = new Error("Network error");
    mockGetFilterOptions.mockRejectedValueOnce(serviceError);

    renderHeader();

    await waitFor(() =>
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "Erro ao buscar categorias:",
        serviceError,
      ),
    );

    consoleErrorSpy.mockRestore();
  });

  it("does not crash when getFilterOptions throws", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetFilterOptions.mockRejectedValueOnce(new Error("500 Server Error"));

    // If the component throws, render() itself will throw.
    expect(() => renderHeader()).not.toThrow();

    // Wait for rejection to propagate through the effect.
    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );
  });

  it("does not render category links after getFilterOptions throws", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetFilterOptions.mockRejectedValueOnce(new Error("Timeout"));

    renderHeader();

    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    const categoryLinks = screen
      .getAllByRole("link")
      .filter((link) =>
        (link.getAttribute("href") ?? "").startsWith("/products?category="),
      );
    expect(categoryLinks).toHaveLength(0);
  });
});

// ── Active link styling ───────────────────────────────────────────────────────

describe("Header - active link styling", () => {
  const categories = [
    { id: 1, name: "Esteiras", slug: "esteiras" },
    { id: 2, name: "Bicicletas", slug: "bicicletas" },
  ];

  it("applies active class to the link matching the current category query param", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader("/products?category=esteiras");

    const activeLink = await screen.findByRole("link", { name: "Esteiras" });

    // Active style: bg-white text-header font-semibold
    expect(activeLink.className).toContain("bg-white");
    expect(activeLink.className).toContain("text-header");
    expect(activeLink.className).toContain("font-semibold");
  });

  it("does not apply active class to a non-matching category link", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader("/products?category=esteiras");

    const inactiveLink = await screen.findByRole("link", {
      name: "Bicicletas",
    });

    // Active state adds "text-header font-semibold"; inactive state uses "text-white".
    // "text-header" is the discriminating active-only token — it must be absent.
    expect(inactiveLink.className).not.toContain("text-header");
    expect(inactiveLink.className).toContain("bg-blue-900");
  });

  it("does not apply active class to any link when pathname is not /products", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    // Same query string but on a different page — active should not trigger.
    renderHeader("/?category=esteiras");

    const link = await screen.findByRole("link", { name: "Esteiras" });

    // Active state sets "text-header"; it must be absent on a non-/products page.
    expect(link.className).not.toContain("text-header");
    expect(link.className).toContain("bg-blue-900");
  });

  it("does not apply active class when on /products but category param does not match", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader("/products?category=halteres");

    const link = await screen.findByRole("link", { name: "Esteiras" });

    // "text-header" is the discriminating active-only token — must be absent.
    expect(link.className).not.toContain("text-header");
  });

  it("does not apply active class to any link when /products has no category param", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions(categories));

    renderHeader("/products");

    const link = await screen.findByRole("link", { name: "Esteiras" });

    expect(link.className).not.toContain("text-header");
    expect(link.className).toContain("bg-blue-900");
  });
});

// ── Static navigation ─────────────────────────────────────────────────────────

describe("Header - static navigation", () => {
  it("renders a link to the home page", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));

    renderHeader();

    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    expect(
      screen.getByRole("link", { name: /página inicial/i }),
    ).toHaveAttribute("href", "/");
  });

  it("renders login and register links when user is not authenticated", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));
    mockUseAuth.mockReturnValue({ isAuthenticated: false });

    renderHeader();

    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    expect(screen.getByRole("link", { name: /entrar/i })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.getByRole("link", { name: /cadastrar/i })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("does not render login/register links when user is authenticated", async () => {
    mockGetFilterOptions.mockResolvedValueOnce(makeFilterOptions([]));
    mockUseAuth.mockReturnValue({ isAuthenticated: true });

    renderHeader();

    await waitFor(() =>
      expect(mockGetFilterOptions).toHaveBeenCalledTimes(1),
    );

    expect(
      screen.queryByRole("link", { name: /entrar/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /cadastrar/i }),
    ).not.toBeInTheDocument();
  });
});
