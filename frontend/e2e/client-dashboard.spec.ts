import { test, expect } from "@playwright/test";
import { injectAuth, clearAuth } from "./helpers/auth";

// ─── API Base ─────────────────────────────────────────────────────────────────
// The app calls http://localhost:8000 (VITE_API_URL default from constants.ts)
const API = "http://localhost:8000";

// ─── Mock Fixtures ────────────────────────────────────────────────────────────

const MOCK_LISTINGS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 101,
      product: { id: 1, name: "Produto Alpha", slug: "produto-alpha", code: null },
      seller: 1,
      seller_name: "Test User",
      title: "Anúncio de Teste Alpha",
      price: "299.90",
      brand: { id: 1, name: "BrandX", slug: "brandx", logo: null },
      quantity: 1,
      is_active: true,
      description: "Descrição do anúncio alpha",
      condition: { id: 1, name: "Novo", slug: "novo" },
      views_count: 42,
      created_at: "2025-01-10T10:00:00Z",
      updated_at: "2025-01-10T10:00:00Z",
      sold_at: null,
      images: [],
      primary_image: null,
      seller_shipping_address: null,
    },
    {
      id: 102,
      product: { id: 2, name: "Produto Beta", slug: "produto-beta", code: null },
      seller: 1,
      seller_name: "Test User",
      title: "Anúncio de Teste Beta",
      price: "599.00",
      brand: { id: 2, name: "BrandY", slug: "brandy", logo: null },
      quantity: 1,
      is_active: false,
      description: "Descrição do anúncio beta",
      condition: { id: 2, name: "Usado", slug: "usado" },
      views_count: 7,
      created_at: "2025-01-15T14:00:00Z",
      updated_at: "2025-01-15T14:00:00Z",
      sold_at: null,
      images: [],
      primary_image: null,
      seller_shipping_address: null,
    },
  ],
};

const MOCK_EMPTY_LISTINGS = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

const MOCK_SALES: object[] = [
  {
    id: "order-sale-1",
    order_number: "VND-2025-001",
    total: "299.90",
    status: "completed",
    created_at: "2025-02-01T12:00:00Z",
  },
  {
    id: "order-sale-2",
    order_number: "VND-2025-002",
    total: "599.00",
    status: "pending",
    created_at: "2025-02-10T09:30:00Z",
  },
];

const MOCK_PURCHASES: object[] = [
  {
    id: "order-buy-1",
    order_number: "CMP-2025-001",
    total: "150.00",
    status: "delivered",
    created_at: "2025-01-20T08:00:00Z",
  },
];

const MOCK_REVIEW_STATS = {
  average_rating: 4.5,
  total_reviews: 3,
  rating_breakdown: { 1: 0, 2: 0, 3: 1, 4: 0, 5: 2 },
};

const MOCK_REVIEWS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      reviewer: { id: 2, full_name: "João Silva", picture: null },
      listing: { id: 101, title: "Anúncio de Teste Alpha" },
      rating: 5,
      comment: "Produto excelente, chegou rápido!",
      created_at: "2025-02-05T10:00:00Z",
    },
    {
      id: 2,
      reviewer: { id: 3, full_name: "Maria Souza", picture: null },
      listing: { id: 101, title: "Anúncio de Teste Alpha" },
      rating: 4,
      comment: "Ótimo produto, recomendo.",
      created_at: "2025-02-08T15:00:00Z",
    },
  ],
};

// ─── Setup Helpers ────────────────────────────────────────────────────────────

/**
 * Registers all default API route mocks for a normal happy-path dashboard load.
 * Must be called before page.goto("/dashboard").
 */
async function mockAllApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/products/my-listings/**`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_LISTINGS),
    });
  });

  await page.route(`${API}/orders/sales/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SALES),
    });
  });

  await page.route(`${API}/orders/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PURCHASES),
    });
  });

  await page.route(`${API}/reviews/stats/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_REVIEW_STATS),
    });
  });

  await page.route(`${API}/reviews/received/**`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_REVIEWS),
    });
  });
}

/**
 * Navigates to the dashboard as an authenticated user with all APIs mocked.
 */
async function goToDashboard(page: import("@playwright/test").Page) {
  await page.goto("/");
  await injectAuth(page);
  await mockAllApis(page);
  await page.goto("/dashboard");
  // Wait for the header banner to confirm the page has fully mounted
  await expect(page.getByText("Painel do vendedor")).toBeVisible();
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Autenticação", () => {
  test("redireciona para /login quando usuário não está autenticado", async ({
    page,
  }) => {
    // Navigate to the base URL first to establish the origin so we can clear storage
    await page.goto("/");
    await clearAuth(page);
    await page.goto("/dashboard");

    // PrivateRoutes redirects unauthenticated users to /login
    await expect(page).toHaveURL(/\/login/);
  });

  test("permite acesso ao dashboard com usuário autenticado", async ({
    page,
  }) => {
    await goToDashboard(page);
    await expect(page).toHaveURL(/\/dashboard/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Banner do cabeçalho", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
  });

  test("exibe o label 'Painel do vendedor'", async ({ page }) => {
    await expect(page.getByText("Painel do vendedor")).toBeVisible();
  });

  test("exibe o primeiro nome do usuário na saudação", async ({ page }) => {
    // MOCK_USER.full_name = "Test User", first name = "Test"
    await expect(page.getByText("Olá, Test!")).toBeVisible();
  });

  test("exibe o avatar com a inicial do primeiro nome quando não há foto", async ({
    page,
  }) => {
    // The avatar renders the first letter of firstName ("T") when picture is empty
    const avatar = page
      .locator(".rounded-full")
      .filter({ hasText: "T" })
      .first();
    await expect(avatar).toBeVisible();
  });

  test("exibe a descrição do painel", async ({ page }) => {
    await expect(
      page.getByText("Gerencie seus anúncios, vendas, compras e avaliações"),
    ).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Navegação por abas", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
  });

  test("renderiza as 5 abas corretamente", async ({ page }) => {
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(5);
  });

  test("exibe os labels das 5 abas em telas desktop", async ({ page }) => {
    // Labels are visible on sm+ via "hidden sm:inline" — desktop viewport passes
    await expect(page.getByRole("tab", { name: /Visão Geral/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Anúncios/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Vendas/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Compras/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Avaliações/i })).toBeVisible();
  });

  test("a aba 'Visão Geral' está ativa por padrão", async ({ page }) => {
    const overviewTab = page.getByRole("tab", { name: /Visão Geral/i });
    await expect(overviewTab).toHaveAttribute("aria-selected", "true");
  });

  test("as demais abas não estão ativas por padrão", async ({ page }) => {
    const inactiveTabs = [/Anúncios/i, /Vendas/i, /Compras/i, /Avaliações/i];
    for (const name of inactiveTabs) {
      const tab = page.getByRole("tab", { name });
      await expect(tab).toHaveAttribute("aria-selected", "false");
    }
  });

  test("clicar em 'Anúncios' torna a aba ativa", async ({ page }) => {
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    await expect(
      page.getByRole("tab", { name: /Anúncios/i }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(
      page.getByRole("tab", { name: /Visão Geral/i }),
    ).toHaveAttribute("aria-selected", "false");
  });

  test("clicar em 'Vendas' torna a aba ativa", async ({ page }) => {
    await page.getByRole("tab", { name: /Vendas/i }).click();
    await expect(page.getByRole("tab", { name: /Vendas/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("clicar em 'Compras' torna a aba ativa", async ({ page }) => {
    await page.getByRole("tab", { name: /Compras/i }).click();
    await expect(
      page.getByRole("tab", { name: /Compras/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  test("clicar em 'Avaliações' torna a aba ativa", async ({ page }) => {
    await page.getByRole("tab", { name: /Avaliações/i }).click();
    await expect(
      page.getByRole("tab", { name: /Avaliações/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  test("clicar em cada aba exibe o conteúdo correto da seção", async ({
    page,
  }) => {
    // Listings section shows listing count
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();

    // Sales section shows order numbers
    await page.getByRole("tab", { name: /Vendas/i }).click();
    await expect(page.getByText("Pedido #VND-2025-001")).toBeVisible();

    // Purchases section shows purchase order numbers
    await page.getByRole("tab", { name: /Compras/i }).click();
    await expect(page.getByText("Pedido #CMP-2025-001")).toBeVisible();

    // Reviews section shows reviewer name
    await page.getByRole("tab", { name: /Avaliações/i }).click();
    await expect(page.getByText("João Silva")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Visão Geral", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
  });

  test("exibe os 4 cards de estatísticas", async ({ page }) => {
    // Labels on the stat cards (uppercase via CSS, queried case-insensitive)
    await expect(page.getByText("Vendas", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Receita", { exact: false })).toBeVisible();
    await expect(page.getByText("Anúncios ativos", { exact: false })).toBeVisible();
    await expect(page.getByText("Avaliação média", { exact: false })).toBeVisible();
  });

  test("exibe o valor calculado de vendas no card", async ({ page }) => {
    // MOCK_SALES has 2 items, so totalSales = 2
    await expect(page.getByText("2").first()).toBeVisible();
  });

  test("exibe os 4 links de acesso rápido", async ({ page }) => {
    await expect(page.getByRole("button", { name: /Meus Anúncios/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Minhas Vendas/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Minhas Compras/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Avaliações/i })).toBeVisible();
  });

  test("clicar em 'Meus Anúncios' navega para a aba de anúncios", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /Meus Anúncios/i }).click();
    await expect(
      page.getByRole("tab", { name: /Anúncios/i }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();
  });

  test("clicar em 'Minhas Vendas' navega para a aba de vendas", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /Minhas Vendas/i }).click();
    await expect(page.getByRole("tab", { name: /Vendas/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByText("Pedido #VND-2025-001")).toBeVisible();
  });

  test("clicar em 'Minhas Compras' navega para a aba de compras", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /Minhas Compras/i }).click();
    await expect(
      page.getByRole("tab", { name: /Compras/i }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Pedido #CMP-2025-001")).toBeVisible();
  });

  test("clicar em 'Avaliações' (quick link) navega para a aba de avaliações", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /Avaliações/i }).first().click();
    await expect(
      page.getByRole("tab", { name: /Avaliações/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  test("CTA 'Anunciar produto' aponta para /create-listing", async ({ page }) => {
    const ctaLink = page.getByRole("link", { name: /Anunciar produto/i });
    await expect(ctaLink).toBeVisible();
    await expect(ctaLink).toHaveAttribute("href", "/create-listing");
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Anúncios (com dados)", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    // Wait for the loading skeleton to be replaced by real content
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();
  });

  test("exibe o botão 'Novo anúncio' apontando para /create-listing", async ({
    page,
  }) => {
    const newListingLink = page.getByRole("link", { name: /Novo anúncio/i });
    await expect(newListingLink).toBeVisible();
    await expect(newListingLink).toHaveAttribute("href", "/create-listing");
  });

  test("exibe as linhas de anúncios com título e preço", async ({ page }) => {
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();
    await expect(page.getByText("Anúncio de Teste Beta")).toBeVisible();
    await expect(page.getByText(/299,90/)).toBeVisible();
    await expect(page.getByText(/599,00/)).toBeVisible();
  });

  test("exibe a contagem de visualizações dos anúncios", async ({ page }) => {
    await expect(page.getByText("42 visualizações")).toBeVisible();
    await expect(page.getByText("7 visualizações")).toBeVisible();
  });

  test("exibe o badge 'Ativo' com ponto verde para anúncio ativo", async ({
    page,
  }) => {
    // The active badge is rendered by ListingStatusBadge with is_active=true
    const activeBadge = page.getByText("Ativo");
    await expect(activeBadge).toBeVisible();
    // The badge container has the green styling
    await expect(activeBadge).toHaveClass(/text-green-700/);
  });

  test("exibe o badge 'Inativo' para anúncio inativo", async ({ page }) => {
    const inactiveBadge = page.getByText("Inativo");
    await expect(inactiveBadge).toBeVisible();
    await expect(inactiveBadge).toHaveClass(/text-red-600/);
  });

  test("exibe os botões de ação para cada anúncio não vendido", async ({
    page,
  }) => {
    // Each non-sold listing has: toggle, edit, delete buttons
    const toggleButtons = page.getByRole("button", {
      name: /Desativar anúncio|Ativar anúncio/i,
    });
    await expect(toggleButtons).toHaveCount(2);

    const editLinks = page.getByRole("link", { name: /Editar anúncio/i });
    await expect(editLinks).toHaveCount(2);

    const deleteButtons = page.getByRole("button", { name: /Excluir anúncio/i });
    await expect(deleteButtons).toHaveCount(2);
  });

  test("o link de edição aponta para /ad/:id", async ({ page }) => {
    const editLinks = page.getByRole("link", { name: /Editar anúncio/i });
    const firstEditHref = await editLinks.first().getAttribute("href");
    expect(firstEditHref).toMatch(/\/ad\/\d+/);
  });

  test("exibe o contador de anúncios na linha de cabeçalho", async ({
    page,
  }) => {
    await expect(page.getByText("2 anúncios")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Anúncios (estado vazio)", () => {
  test("exibe o empty state quando não há anúncios", async ({ page }) => {
    await page.goto("/");
    await injectAuth(page);

    // Override listings to return empty
    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_EMPTY_LISTINGS),
      });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Anúncios/i }).click();

    await expect(
      page.getByText("Você não tem anúncios ainda"),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Criar anúncio/i }),
    ).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Skeleton de carregamento", () => {
  test("exibe 4 linhas de skeleton enquanto os anúncios são carregados", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    // Delay the listings response so we can observe the skeleton
    await page.route(`${API}/products/my-listings/**`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_LISTINGS),
      });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_SALES) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PURCHASES) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_REVIEW_STATS) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_REVIEWS) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Anúncios/i }).click();

    // The skeleton renders 4 rows with animate-pulse
    const skeletonRows = page.locator(".animate-pulse");
    await expect(skeletonRows).toHaveCount(4);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Vendas (com dados)", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Vendas/i }).click();
    await expect(page.getByText("Pedido #VND-2025-001")).toBeVisible();
  });

  test("exibe os pedidos de venda com número e total", async ({ page }) => {
    await expect(page.getByText("Pedido #VND-2025-001")).toBeVisible();
    await expect(page.getByText("Pedido #VND-2025-002")).toBeVisible();
    await expect(page.getByText(/299,90/)).toBeVisible();
    await expect(page.getByText(/599,00/)).toBeVisible();
  });

  test("exibe o badge de status 'Pendente' para pedido com status pending", async ({
    page,
  }) => {
    const pendenteBadge = page.getByText("Pendente");
    await expect(pendenteBadge).toBeVisible();
    await expect(pendenteBadge).toHaveClass(/text-yellow-800/);
  });

  test("exibe o badge de status 'Concluído' para pedido com status completed", async ({
    page,
  }) => {
    const concluídoBadge = page.getByText("Concluído");
    await expect(concluídoBadge).toBeVisible();
    await expect(concluídoBadge).toHaveClass(/text-green-800/);
  });

  test("exibe a data do pedido no formato pt-BR", async ({ page }) => {
    // 2025-02-01 → "01/02/2025" in pt-BR
    await expect(page.getByText("01/02/2025")).toBeVisible();
  });

  test("exibe o contador de vendas no cabeçalho da seção", async ({ page }) => {
    await expect(page.getByText("2 vendas")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Vendas (estado vazio)", () => {
  test("exibe o empty state quando não há vendas", async ({ page }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Vendas/i }).click();
    await expect(
      page.getByText("Nenhuma venda realizada ainda"),
    ).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Compras (com dados)", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Compras/i }).click();
    await expect(page.getByText("Pedido #CMP-2025-001")).toBeVisible();
  });

  test("exibe os pedidos de compra com número e total", async ({ page }) => {
    await expect(page.getByText("Pedido #CMP-2025-001")).toBeVisible();
    await expect(page.getByText(/150,00/)).toBeVisible();
  });

  test("exibe o badge 'Entregue' para pedido com status delivered", async ({
    page,
  }) => {
    const entregue = page.getByText("Entregue");
    await expect(entregue).toBeVisible();
    await expect(entregue).toHaveClass(/text-green-800/);
  });

  test("exibe o contador de compras no cabeçalho da seção", async ({ page }) => {
    await expect(page.getByText("1 compra")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Compras (estado vazio)", () => {
  test("exibe empty state com CTA 'Explorar produtos' apontando para /", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EMPTY_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Compras/i }).click();

    await expect(page.getByText("Nenhuma compra realizada")).toBeVisible();

    const ctaLink = page.getByRole("link", { name: /Explorar produtos/i });
    await expect(ctaLink).toBeVisible();
    await expect(ctaLink).toHaveAttribute("href", "/");
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Avaliações (com dados)", () => {
  test.beforeEach(async ({ page }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Avaliações/i }).click();
    await expect(page.getByText("João Silva")).toBeVisible();
  });

  test("exibe o painel de resumo de rating com média", async ({ page }) => {
    // Stats panel shows average_rating = 4.5 formatted to 1 decimal
    await expect(page.getByText("4.5")).toBeVisible();
  });

  test("exibe o total de avaliações no painel de estatísticas", async ({
    page,
  }) => {
    await expect(page.getByText(/3 avalia/i)).toBeVisible();
  });

  test("exibe os nomes dos revisores", async ({ page }) => {
    await expect(page.getByText("João Silva")).toBeVisible();
    await expect(page.getByText("Maria Souza")).toBeVisible();
  });

  test("exibe o comentário da avaliação no balão de citação", async ({
    page,
  }) => {
    await expect(
      page.getByText("Produto excelente, chegou rápido!"),
    ).toBeVisible();
    await expect(
      page.getByText("Ótimo produto, recomendo."),
    ).toBeVisible();
  });

  test("exibe o título do anúncio avaliado", async ({ page }) => {
    const listingRefs = page.getByText(/Anúncio: Anúncio de Teste Alpha/);
    await expect(listingRefs.first()).toBeVisible();
  });

  test("exibe as barras do breakdown de rating", async ({ page }) => {
    // 5 bars for star ratings 5, 4, 3, 2, 1
    // The breakdown section has the labels 5, 4, 3, 2, 1 as text
    // They're rendered inside a flex row with star icons
    const starLabels = ["5", "4", "3", "2", "1"];
    for (const label of starLabels) {
      // Each rating row in the breakdown has the star number as text
      await expect(
        page.locator(".space-y-2 span").filter({ hasText: label }).first(),
      ).toBeVisible();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Aba Avaliações (estado vazio)", () => {
  test("exibe empty state 'Nenhuma avaliação recebida' quando não há avaliações", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_SALES) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PURCHASES) });
    });
    // Stats with no reviews — the summary panel must NOT appear
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          average_rating: 0,
          total_reviews: 0,
          rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 },
        }),
      });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
      });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Avaliações/i }).click();

    await expect(
      page.getByText("Nenhuma avaliação recebida"),
    ).toBeVisible();
  });

  test("não exibe o painel de estatísticas quando total_reviews é 0", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }),
      });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
      });
    });

    await page.goto("/dashboard");
    await page.getByRole("tab", { name: /Avaliações/i }).click();

    // The stats panel (gradient background) is conditionally rendered only when total_reviews > 0
    await expect(
      page.locator(".bg-gradient-to-br.from-blue-50"),
    ).not.toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Estados de erro e retry", () => {
  test("exibe mensagem de erro e botão 'Tentar novamente' quando /products/my-listings/ retorna 500", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Internal Server Error" }) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Anúncios/i }).click();

    await expect(
      page.getByText("Erro ao carregar seus anúncios."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tentar novamente/i }),
    ).toBeVisible();
  });

  test("exibe mensagem de erro e botão 'Tentar novamente' quando /orders/sales/ retorna 500", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Server error" }) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Vendas/i }).click();

    await expect(
      page.getByText("Erro ao carregar suas vendas."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tentar novamente/i }),
    ).toBeVisible();
  });

  test("exibe mensagem de erro e botão 'Tentar novamente' quando /orders/ retorna 500", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Server error" }) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Compras/i }).click();

    await expect(
      page.getByText("Erro ao carregar suas compras."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tentar novamente/i }),
    ).toBeVisible();
  });

  test("exibe mensagem de erro e botão 'Tentar novamente' quando /reviews/received/ retorna 500", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Server error" }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();

    await page.getByRole("tab", { name: /Avaliações/i }).click();

    await expect(
      page.getByText("Erro ao carregar avaliações."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tentar novamente/i }),
    ).toBeVisible();
  });

  test("clicar em 'Tentar novamente' realiza nova chamada à API de anúncios", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    let callCount = 0;

    await page.route(`${API}/products/my-listings/**`, (route) => {
      callCount++;
      if (callCount === 1) {
        route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Server error" }) });
      } else {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_LISTINGS) });
      }
    });
    await page.route(`${API}/orders/sales/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/orders/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
    });
    await page.route(`${API}/reviews/stats/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
    });
    await page.route(`${API}/reviews/received/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
    });

    await page.goto("/dashboard");
    await expect(page.getByText("Painel do vendedor")).toBeVisible();
    await page.getByRole("tab", { name: /Anúncios/i }).click();

    // First attempt fails — error state is shown
    await expect(
      page.getByText("Erro ao carregar seus anúncios."),
    ).toBeVisible();

    // Retry — second call succeeds
    await page.getByRole("button", { name: /Tentar novamente/i }).click();

    // After retry, real data appears
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();
    expect(callCount).toBe(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Exclusão de anúncio", () => {
  test("exibe diálogo de confirmação ao clicar em excluir", async ({ page }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();

    // Intercept the confirm dialog — accept it
    page.on("dialog", (dialog) => dialog.accept());

    // Mock the delete endpoint
    await page.route(`${API}/products/listings/101/delete/`, (route) => {
      route.fulfill({ status: 204, body: "" });
    });

    const deleteButtons = page.getByRole("button", { name: /Excluir anúncio/i });
    await deleteButtons.first().click();

    // After confirm + successful delete, the listing is removed from the DOM
    await expect(page.getByText("Anúncio de Teste Alpha")).not.toBeVisible();
  });

  test("não exclui o anúncio quando o usuário cancela o diálogo", async ({
    page,
  }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();

    // Dismiss the confirm dialog
    page.on("dialog", (dialog) => dialog.dismiss());

    const deleteButtons = page.getByRole("button", { name: /Excluir anúncio/i });
    await deleteButtons.first().click();

    // Listing must remain visible
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Toggle de anúncio ativo/inativo", () => {
  test("clicar em toggle ativo chama a API e inverte o estado visual", async ({
    page,
  }) => {
    await goToDashboard(page);
    await page.getByRole("tab", { name: /Anúncios/i }).click();
    await expect(page.getByText("Anúncio de Teste Alpha")).toBeVisible();

    // Mock the toggle endpoint
    await page.route(`${API}/products/listings/101/activate/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ message: "ok", is_active: false }),
      });
    });

    // First listing (id=101) is active — button is labeled "Desativar anúncio"
    const toggleButton = page
      .getByRole("button", { name: /Desativar anúncio/i })
      .first();
    await expect(toggleButton).toBeVisible();
    await toggleButton.click();

    // After toggle, the badge for the first listing should change to Inativo
    // (The second listing was already Inativo, so we now expect 2 "Inativo" badges)
    await expect(page.getByText("Inativo").first()).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Responsividade Mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("exibe as 5 abas na viewport mobile", async ({ page }) => {
    await goToDashboard(page);
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(5);
  });

  test("banner do cabeçalho permanece visível em mobile", async ({ page }) => {
    await goToDashboard(page);
    await expect(page.getByText("Painel do vendedor")).toBeVisible();
    await expect(page.getByText("Olá, Test!")).toBeVisible();
  });

  test("cards de estatísticas são renderizados em grade de 2 colunas em mobile", async ({
    page,
  }) => {
    await goToDashboard(page);
    // The grid has `grid-cols-2 lg:grid-cols-4`
    // On mobile, all 4 stat cards must still be present in the DOM
    await expect(page.getByText("Vendas", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Receita", { exact: false })).toBeVisible();
    await expect(page.getByText("Anúncios ativos", { exact: false })).toBeVisible();
    await expect(page.getByText("Avaliação média", { exact: false })).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────

test.describe("ClientDashboard - Badges de status de pedido (mapeamento completo)", () => {
  const STATUS_CASES: [string, string, string][] = [
    ["pending",    "Pendente",        "text-yellow-800"],
    ["processing", "Em processamento","text-blue-800"],
    ["shipped",    "Enviado",         "text-purple-800"],
    ["delivered",  "Entregue",        "text-green-800"],
    ["completed",  "Concluído",       "text-green-800"],
    ["cancelled",  "Cancelado",       "text-red-800"],
  ];

  for (const [status, expectedLabel, expectedColor] of STATUS_CASES) {
    test(`status '${status}' renderiza badge '${expectedLabel}'`, async ({
      page,
    }) => {
      await page.goto("/");
      await injectAuth(page);

      const mockOrder = [{
        id: `order-status-${status}`,
        order_number: `ORD-STATUS-${status.toUpperCase()}`,
        total: "100.00",
        status,
        created_at: "2025-01-01T00:00:00Z",
      }];

      await page.route(`${API}/products/my-listings/**`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_EMPTY_LISTINGS) });
      });
      await page.route(`${API}/orders/sales/`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockOrder) });
      });
      await page.route(`${API}/orders/`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      });
      await page.route(`${API}/reviews/stats/`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ average_rating: 0, total_reviews: 0, rating_breakdown: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } }) });
      });
      await page.route(`${API}/reviews/received/**`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
      });

      await page.goto("/dashboard");
      await expect(page.getByText("Painel do vendedor")).toBeVisible();
      await page.getByRole("tab", { name: /Vendas/i }).click();

      const badge = page.getByText(expectedLabel);
      await expect(badge).toBeVisible();
      await expect(badge).toHaveClass(new RegExp(expectedColor));
    });
  }
});
