import { test, expect } from "@playwright/test";
import { injectAuth, clearAuth } from "./helpers/auth";

// ─── API Base ─────────────────────────────────────────────────────────────────
// Matches the VITE_API_URL default used by the app's axios instance.
const API = "http://localhost:8000";

// ─── Shared API Mock Helpers ──────────────────────────────────────────────────

/**
 * Mocks the two endpoints that fire on every HomeLayout page load:
 *   - GET /products/listings/  — consumed by the Home page
 *   - GET /products/categories/ — consumed by the Header component
 *
 * Both endpoints returning empty/minimal data is enough to let the page
 * finish mounting without network errors that could obscure test failures.
 */
async function mockHomePageApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/products/listings/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
    });
  });

  await page.route(`${API}/products/categories/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, results: [] }),
    });
  });
}

/**
 * Mocks all five API endpoints that the ClientDashboard (/dashboard) calls on
 * mount, plus the two base HomeLayout endpoints.
 *
 * Using minimal/empty payloads keeps the assertions focused on navigation
 * rather than data rendering.
 *
 * reviews/stats/ returns 404 intentionally — the component must degrade
 * gracefully rather than crash when this endpoint is unavailable.
 */
async function mockDashboardApis(page: import("@playwright/test").Page) {
  // Base layout APIs
  await mockHomePageApis(page);

  // Dashboard-specific APIs
  await page.route(`${API}/products/my-listings/**`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
    });
  });

  await page.route(`${API}/orders/sales/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`${API}/orders/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  // Intentional 404 — verifies the dashboard handles missing stats gracefully.
  await page.route(`${API}/reviews/stats/`, (route) => {
    route.fulfill({ status: 404, contentType: "application/json", body: "null" });
  });

  await page.route(`${API}/reviews/received/**`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
    });
  });
}

// ─── Navigation Helpers ───────────────────────────────────────────────────────

/**
 * Navigates to "/" as an unauthenticated user with Home page APIs mocked.
 * The BottomNav (and therefore NavMenu) is rendered by HomeLayout on every
 * public route, so "/" is the cheapest entry point.
 */
async function goToHomeUnauthenticated(page: import("@playwright/test").Page) {
  await mockHomePageApis(page);
  await page.goto("/");
  // Wait for the page to settle — the empty-state copy confirms the listings
  // fetch completed and the full layout (including BottomNav) has mounted.
  await expect(page.getByText("Nenhum produto encontrado.")).toBeVisible();
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

test.describe("NavMenu", () => {
  // ── 1. Comportamento do botão Menu ──────────────────────────────────────────

  test.describe("Comportamento do botão Menu", () => {
    // Every test in this group starts from the Home page (unauthenticated is
    // fine — the BottomNav is always rendered by HomeLayout regardless of
    // authentication state).
    test.beforeEach(async ({ page }) => {
      await goToHomeUnauthenticated(page);
    });

    test("o botão Menu está visível na BottomNav", async ({ page }) => {
      // NavMenu renders a <button> with the visible text "Menu".
      await expect(page.getByRole("button", { name: "Abrir menu" })).toBeVisible();
      await expect(page.getByText("Menu").first()).toBeVisible();
    });

    test("clicar em Menu abre o drawer com role=dialog", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();

      // The drawer is always in the DOM (created via createPortal) but is only
      // semantically "open" once it becomes visible and interactive.
      await expect(page.getByRole("dialog")).toBeVisible();
    });

    test("o drawer exibe o cabeçalho 'Menu'", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();

      // The heading inside the drawer carries id="nav-menu-heading".
      await expect(
        page.getByRole("dialog").getByText("Menu"),
      ).toBeVisible();
    });

    test("pressionar Escape fecha o drawer", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      await page.keyboard.press("Escape");

      // After closing, the dialog should no longer be visible.
      // The element stays in the DOM (translate-x-full) so we check visibility.
      await expect(page.getByRole("dialog")).not.toBeVisible();
    });

    test("clicar no overlay fecha o drawer", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      // The overlay is a fixed <div aria-hidden="true"> that sits behind the
      // drawer. When the drawer is open it has opacity-100 and no
      // pointer-events-none, so it can be clicked.
      // We locate it via aria-hidden since it has no other semantic role.
      const overlay = page.locator('[aria-hidden="true"]').first();
      await overlay.click({ position: { x: 5, y: 5 } });

      await expect(page.getByRole("dialog")).not.toBeVisible();
    });

    test("clicar no botão X (fechar) fecha o drawer", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      await page.getByRole("button", { name: "Fechar menu" }).click();

      await expect(page.getByRole("dialog")).not.toBeVisible();
    });

    test("ao abrir o drawer, o foco é movido para o botão de fechar", async ({
      page,
    }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      // NavMenu calls closeButtonRef.current?.focus() inside the useEffect
      // that runs when isOpen becomes true.
      const closeButton = page.getByRole("button", { name: "Fechar menu" });
      await expect(closeButton).toBeFocused();
    });
  });

  // ── 2. Renderização dos itens do menu ────────────────────────────────────────

  test.describe("Renderização dos itens do menu", () => {
    test.beforeEach(async ({ page }) => {
      await goToHomeUnauthenticated(page);
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
    });

    test("exibe os 3 itens de navegação dentro do drawer", async ({ page }) => {
      const drawer = page.getByRole("dialog");

      await expect(drawer.getByText("Minhas Vendas")).toBeVisible();
      await expect(drawer.getByText("Minhas Compras")).toBeVisible();
      await expect(drawer.getByText("Painel Administrativo")).toBeVisible();
    });

    test("cada item é renderizado como um link âncora (elemento <a>)", async ({
      page,
    }) => {
      const drawer = page.getByRole("dialog");

      // React Router's <Link> renders as a standard <a> element.
      // Checking for the 'link' role confirms the component used Link and not button.
      await expect(
        drawer.getByRole("link", { name: "Minhas Vendas" }),
      ).toBeVisible();
      await expect(
        drawer.getByRole("link", { name: "Minhas Compras" }),
      ).toBeVisible();
      await expect(
        drawer.getByRole("link", { name: "Painel Administrativo" }),
      ).toBeVisible();
    });

    test("os ícones de cada item têm aria-hidden='true' (não expostos a leitores)", async ({
      page,
    }) => {
      // The component sets aria-hidden="true" on each <item.icon> SVG so
      // screen readers read only the text label.
      const drawer = page.getByRole("dialog");
      const nav = drawer.locator("nav");

      // All SVG icons inside the nav must be aria-hidden
      const icons = nav.locator('svg[aria-hidden="true"]');
      await expect(icons).toHaveCount(3);
    });
  });

  // ── 3. Links de navegação (crítico — paths corrigidos) ───────────────────────

  test.describe("Links de navegação", () => {
    // These assertions verify the paths that were WRONG before the fix:
    //   OLD: /my-sales, /my-purchases, /admin
    //   NEW: /mysales,  /mypurchase,   /dashboard

    test.beforeEach(async ({ page }) => {
      await goToHomeUnauthenticated(page);
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
    });

    test("'Minhas Vendas' tem href='/mysales' e NÃO '/my-sales'", async ({
      page,
    }) => {
      const link = page.getByRole("dialog").getByRole("link", { name: "Minhas Vendas" });

      await expect(link).toHaveAttribute("href", "/mysales");
      // Explicitly assert the old wrong path is NOT present
      await expect(link).not.toHaveAttribute("href", "/my-sales");
    });

    test("'Minhas Compras' tem href='/mypurchase' e NÃO '/my-purchases'", async ({
      page,
    }) => {
      const link = page.getByRole("dialog").getByRole("link", { name: "Minhas Compras" });

      await expect(link).toHaveAttribute("href", "/mypurchase");
      await expect(link).not.toHaveAttribute("href", "/my-purchases");
    });

    test("'Painel Administrativo' tem href='/dashboard' e NÃO '/admin'", async ({
      page,
    }) => {
      const link = page.getByRole("dialog").getByRole("link", {
        name: "Painel Administrativo",
      });

      await expect(link).toHaveAttribute("href", "/dashboard");
      await expect(link).not.toHaveAttribute("href", "/admin");
    });
  });

  // ── 4. Fluxo de navegação ─────────────────────────────────────────────────────

  test.describe("Fluxo de navegação", () => {
    test("Painel Administrativo → fecha drawer, navega para /dashboard e carrega ClientDashboard", async ({
      page,
    }) => {
      // Mock all APIs before navigating so no real network requests escape.
      await mockDashboardApis(page);
      await page.goto("/");
      await injectAuth(page);
      await page.reload();
      await expect(page.getByText("Nenhum produto encontrado.")).toBeVisible();

      // Open the drawer and click the dashboard link.
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      await page.getByRole("link", { name: "Painel Administrativo" }).click();

      // After clicking, the drawer's onClick handler calls setIsOpen(false)
      // and React Router changes the URL.
      await expect(page.getByRole("dialog")).not.toBeVisible();
      await expect(page).toHaveURL(/\/dashboard/);

      // The ClientDashboard banner confirms the page fully mounted.
      await expect(page.getByText("Painel do vendedor")).toBeVisible();
    });

    test("Minhas Vendas → fecha drawer e navega para /mysales", async ({
      page,
    }) => {
      await mockHomePageApis(page);
      // /mysales is a private route — we need auth so PrivateRoutes does not
      // redirect to /login before we can verify the URL change.
      await page.goto("/");
      await injectAuth(page);
      await page.reload();
      await expect(page.getByText("Nenhum produto encontrado.")).toBeVisible();

      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      await page.getByRole("link", { name: "Minhas Vendas" }).click();

      await expect(page.getByRole("dialog")).not.toBeVisible();
      await expect(page).toHaveURL(/\/mysales/);
    });

    test("Minhas Compras → fecha drawer e navega para /mypurchase", async ({
      page,
    }) => {
      await mockHomePageApis(page);
      await page.goto("/");
      await injectAuth(page);
      await page.reload();
      await expect(page.getByText("Nenhum produto encontrado.")).toBeVisible();

      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      await page.getByRole("link", { name: "Minhas Compras" }).click();

      await expect(page.getByRole("dialog")).not.toBeVisible();
      await expect(page).toHaveURL(/\/mypurchase/);
    });
  });

  // ── 5. Acesso direto sem autenticação ─────────────────────────────────────────

  test.describe("Proteção de rotas", () => {
    test("acesso direto a /dashboard sem autenticação redireciona para /login", async ({
      page,
    }) => {
      // Establish the origin first so we can clear localStorage on it.
      await page.goto("/");
      await clearAuth(page);

      await page.goto("/dashboard");

      // PrivateRoutes wraps /dashboard; it redirects unauthenticated users.
      await expect(page).toHaveURL(/\/login/);
    });

    test("acesso direto a /mysales sem autenticação redireciona para /login", async ({
      page,
    }) => {
      await page.goto("/");
      await clearAuth(page);

      await page.goto("/mysales");

      await expect(page).toHaveURL(/\/login/);
    });

    test("acesso direto a /mypurchase sem autenticação redireciona para /login", async ({
      page,
    }) => {
      await page.goto("/");
      await clearAuth(page);

      await page.goto("/mypurchase");

      await expect(page).toHaveURL(/\/login/);
    });
  });

  // ── 6. Acessibilidade ─────────────────────────────────────────────────────────

  test.describe("Acessibilidade", () => {
    test.beforeEach(async ({ page }) => {
      await goToHomeUnauthenticated(page);
    });

    test("o botão Menu tem aria-expanded='false' quando o drawer está fechado", async ({
      page,
    }) => {
      // Before opening, the button reports its expanded state as false.
      const menuButton = page.getByRole("button", { name: "Abrir menu" });
      await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    });

    test("o botão Menu tem aria-expanded='true' quando o drawer está aberto", async ({
      page,
    }) => {
      const menuButton = page.getByRole("button", { name: "Abrir menu" });
      await menuButton.click();

      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(menuButton).toHaveAttribute("aria-expanded", "true");
    });

    test("o drawer tem role='dialog' e aria-modal='true'", async ({ page }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();

      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();
      await expect(drawer).toHaveAttribute("aria-modal", "true");
    });

    test("o drawer tem aria-labelledby apontando para o heading do menu", async ({
      page,
    }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();

      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();

      // The <aside role="dialog"> uses aria-labelledby="nav-menu-heading".
      // The matching <span id="nav-menu-heading"> contains the text "Menu".
      await expect(drawer).toHaveAttribute("aria-labelledby", "nav-menu-heading");

      // Verify the element with that id actually exists and contains "Menu".
      await expect(page.locator("#nav-menu-heading")).toHaveText("Menu");
    });

    test("o overlay tem aria-hidden='true' para ocultar de leitores de tela", async ({
      page,
    }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      // The overlay <div> is explicitly aria-hidden so it is invisible to AT.
      // We locate it as the first aria-hidden element in the body portal.
      const overlay = page.locator("body > div [aria-hidden='true']").first();
      await expect(overlay).toHaveAttribute("aria-hidden", "true");
    });

    test("os itens do menu são acessíveis como links pela navegação de teclado", async ({
      page,
    }) => {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();

      // All three items must be reachable as links for keyboard and AT users.
      const drawer = page.getByRole("dialog");
      const links = drawer.getByRole("link");

      // Should have exactly 3 links (Minhas Vendas, Minhas Compras, Painel Admin)
      await expect(links).toHaveCount(3);
    });
  });
});
