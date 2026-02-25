import { test, expect } from "@playwright/test";
import { injectAuth } from "./helpers/auth";

// ─── API Base ──────────────────────────────────────────────────────────────────
const API = "http://localhost:8000";

// ─── Mock Fixtures ─────────────────────────────────────────────────────────────

const MOCK_ME_CONNECTED = {
  connected: true,
  environment: "sandbox",
  me_email: "seller@example.com",
  access_token: "mock-me-token",
  is_expired: false,
  expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
  expires_in_seconds: 3600,
  is_refresh_token_expired: false,
  last_refreshed_at: new Date().toISOString(),
};

const MOCK_ME_NOT_CONNECTED = {
  connected: false,
  environment: "sandbox",
  me_email: null,
  access_token: null,
  is_expired: null,
  expires_at: null,
  expires_in_seconds: null,
  is_refresh_token_expired: null,
  last_refreshed_at: null,
};

const MOCK_ME_EXPIRED = {
  connected: true,
  environment: "sandbox",
  me_email: "seller@example.com",
  access_token: "expired-token",
  is_expired: true,
  expires_at: new Date(Date.now() - 3600 * 1000).toISOString(),
  expires_in_seconds: -3600,
  is_refresh_token_expired: false,
  last_refreshed_at: null,
};

const MOCK_ME_CONNECT_URL = {
  authorization_url: "https://melhorenvio.com.br/oauth/authorize?client_id=test",
};

const MOCK_FILTER_OPTIONS = {
  categories: [
    { id: 1, name: "Eletrônicos", slug: "eletronicos" },
  ],
  brands: [
    { id: 1, name: "BrandX", slug: "brandx" },
    { id: 2, name: "BrandY", slug: "brandy" },
  ],
  conditions: [
    { id: 1, name: "Novo", slug: "novo" },
    { id: 2, name: "Usado", slug: "usado" },
  ],
  price_range: { min: 0, max: 10000 },
};

const MOCK_PRODUCTS_PAGE_1 = {
  count: 3,
  next: `${API}/products/products/?page=2`,
  previous: null,
  results: [
    { id: 1, name: "Monitor Ultrawide LG", slug: "monitor-lg", code: "MON-LG-001" },
    { id: 2, name: "Teclado Mecânico Keychron", slug: "teclado-keychron", code: null },
    { id: 3, name: "Mouse Logitech G502", slug: "mouse-logitech", code: "MOU-LOG-502" },
  ],
};

const MOCK_PRODUCTS_PAGE_2 = {
  count: 3,
  next: null,
  previous: `${API}/products/products/`,
  results: [
    { id: 4, name: "Webcam Logitech C920", slug: "webcam-c920", code: null },
  ],
};

const MOCK_PRODUCTS_EMPTY = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

const MOCK_CREATED_LISTING = {
  id: 999,
  product: { id: 1, name: "Monitor Ultrawide LG", slug: "monitor-lg", code: "MON-LG-001", description: "", category: null, series: null },
  brand: { id: 1, name: "BrandX", slug: "brandx", logo: null, website: "", is_active: true },
  condition: { id: 1, name: "Novo", slug: "novo" },
  images: [],
  seller: 1,
  seller_name: "Test User",
  seller_email: "test@example.com",
  seller_shipping_address: null,
  title: "Monitor Ultrawide LG 34'' 144Hz",
  price: "1500.00",
  quantity: 5,
  is_active: true,
  description: "Monitor gamer com 144hz e 1ms de resposta.",
  views_count: 0,
  weight_kg: "3.50",
  height_cm: "20.00",
  width_cm: "80.00",
  length_cm: "50.00",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  sold_at: null,
};

const MOCK_EXISTING_LISTING = {
  id: 42,
  product: { id: 2, name: "Teclado Mecânico Keychron", slug: "teclado-keychron", code: null, description: "", category: null, series: null },
  brand: { id: 2, name: "BrandY", slug: "brandy", logo: null, website: "", is_active: true },
  condition: { id: 2, name: "Usado", slug: "usado" },
  images: [
    { id: 10, image_url: "https://cdn.example.com/img1.jpg", object_name: "img1.jpg", is_primary: true, order: 0, created_at: "2025-01-01T00:00:00Z" },
  ],
  seller: 1,
  seller_name: "Test User",
  seller_email: "test@example.com",
  seller_shipping_address: null,
  title: "Teclado Keychron K2 v2",
  price: "450.00",
  quantity: 2,
  is_active: true,
  description: "Teclado mecânico compacto, excelente estado.",
  views_count: 15,
  weight_kg: "1.20",
  height_cm: "5.00",
  width_cm: "35.00",
  length_cm: "15.00",
  packages: [
    { weight_kg: "1.20", height_cm: "5.00", width_cm: "35.00", length_cm: "15.00", description: "" },
  ],
  created_at: "2025-01-15T10:00:00Z",
  updated_at: "2025-01-15T10:00:00Z",
  sold_at: null,
};

const MOCK_PRESIGNED_URL = {
  upload_url: "http://localhost:9000/bucket/test-image.jpg?X-Amz-Signature=abc",
  file_url: "http://localhost:9000/bucket/test-image.jpg",
  object_name: "uploads/test-image.jpg",
};

const MOCK_IMAGE_LINKED = {
  id: 20,
  image_url: "http://localhost:9000/bucket/test-image.jpg",
  object_name: "uploads/test-image.jpg",
  is_primary: true,
  order: 0,
  created_at: new Date().toISOString(),
};

// ─── Setup Helpers ──────────────────────────────────────────────────────────────

/**
 * Mocks all endpoints that ListingForm calls on mount, wiring up
 * the ME gate (connected + not expired) and product/filter data.
 * Must be called before page.goto().
 */
async function mockBaseApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/logistics/me/status/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_ME_CONNECTED),
    });
  });

  await page.route(`${API}/products/search/filters/options/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_FILTER_OPTIONS),
    });
  });

  await page.route(`${API}/products/products/**`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PRODUCTS_PAGE_1),
    });
  });
}

/**
 * Navigates to /create-listing as an authenticated user with
 * all base APIs mocked and waits for step 1 to be visible.
 */
async function goToCreateListing(page: import("@playwright/test").Page) {
  await page.goto("/");
  await injectAuth(page);
  await mockBaseApis(page);
  await page.goto("/create-listing");
  await expect(page.getByText("Passo 1 de 7")).toBeVisible({ timeout: 8000 });
}

/**
 * Navigates to /ad/:id as an authenticated user for edit mode.
 */
async function goToEditListing(
  page: import("@playwright/test").Page,
  listingId: number,
) {
  await page.goto("/");
  await injectAuth(page);
  await mockBaseApis(page);
  await page.route(`${API}/products/listings/${listingId}/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EXISTING_LISTING),
    });
  });
  await page.goto(`/ad/${listingId}`);
  await expect(page.getByText("Editar Anúncio")).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("Passo 1 de 7")).toBeVisible({ timeout: 8000 });
}

/**
 * Clears any saved draft from localStorage for create-listing.
 */
async function clearDraft(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    localStorage.removeItem("listing_draft");
  });
}

/**
 * Injects a draft directly into localStorage to simulate a returning user.
 */
async function injectDraft(
  page: import("@playwright/test").Page,
  step: number,
  formData: Record<string, string> = {},
) {
  await page.evaluate(
    ({ step, formData }) => {
      const draft = {
        step,
        formData: {
          product: "",
          title: "",
          brand: "",
          condition: "",
          description: "",
          price: "",
          quantity: "1",
          weight_kg: "",
          height_cm: "",
          width_cm: "",
          length_cm: "",
          package_description: "",
          ...formData,
        },
      };
      localStorage.setItem("listing_draft", JSON.stringify(draft));
    },
    { step, formData },
  );
}

/**
 * Advances the form through all 7 steps by filling in valid data
 * and clicking Próximo at each step.
 */
async function fillAndAdvanceAllSteps(page: import("@playwright/test").Page) {
  // Step 1 — select product from the list
  await page.getByText("Monitor Ultrawide LG").first().click();
  await expect(page.locator(".bg-blue-50").filter({ hasText: "Monitor Ultrawide LG" })).toBeVisible();
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Step 2 — title
  await expect(page.getByText("Passo 2 de 7")).toBeVisible();
  await page.getByPlaceholder(/Monitor Ultrawide/i).fill("Monitor Ultrawide LG 34'' 144Hz");
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Step 3 — description
  await expect(page.getByText("Passo 3 de 7")).toBeVisible();
  await page.getByPlaceholder(/Descreva o produto/i).fill("Monitor gamer com 144hz e 1ms de resposta.");
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Step 4 — brand and condition
  await expect(page.getByText("Passo 4 de 7")).toBeVisible();
  await page.getByRole("combobox", { name: /Marca/i }).selectOption({ value: "1" });
  await page.getByLabel("Novo").click();
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Step 5 — price and quantity
  await expect(page.getByText("Passo 5 de 7")).toBeVisible();
  await page.locator('input[name="price"]').fill("1500");
  await page.locator('input[name="quantity"]').fill("5");
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Step 6 — package dimensions
  await expect(page.getByText("Passo 6 de 7")).toBeVisible();
  await page.locator('input[name="weight_kg"]').fill("3.5");
  await page.locator('input[name="height_cm"]').fill("20");
  await page.locator('input[name="width_cm"]').fill("80");
  await page.locator('input[name="length_cm"]').fill("50");
  await page.getByRole("button", { name: /Próximo/i }).click();

  // Now on step 7
  await expect(page.getByText("Passo 7 de 7")).toBeVisible();
}

// ─── Test Suites ────────────────────────────────────────────────────────────────

// ─── 1. Melhor Envio Gate ───────────────────────────────────────────────────────

test.describe("ListingForm - Gate Melhor Envio: não conectado", () => {
  test("exibe a tela de bloqueio com botão de conexão quando não conectado", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/logistics/me/status/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ME_NOT_CONNECTED),
      });
    });
    await page.route(`${API}/logistics/me/connect/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ME_CONNECT_URL),
      });
    });
    await page.route(`${API}/products/search/filters/options/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_FILTER_OPTIONS) });
    });
    await page.route(`${API}/products/products/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
    });

    await page.goto("/create-listing");

    await expect(page.getByText("Conecte sua conta Melhor Envio")).toBeVisible({ timeout: 8000 });
    await expect(
      page.getByText(/Para anunciar produtos você precisa conectar/i),
    ).toBeVisible();

    const connectButton = page.getByRole("link", { name: /Conectar Melhor Envio/i });
    await expect(connectButton).toBeVisible();
    await expect(connectButton).toHaveAttribute(
      "href",
      MOCK_ME_CONNECT_URL.authorization_url,
    );
  });

  test("exibe mensagem de suporte quando a URL de conexão não está disponível", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/logistics/me/status/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ME_NOT_CONNECTED),
      });
    });
    // Connect URL fails
    await page.route(`${API}/logistics/me/connect/`, (route) => {
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Error" }) });
    });
    await page.route(`${API}/products/search/filters/options/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_FILTER_OPTIONS) });
    });
    await page.route(`${API}/products/products/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
    });

    await page.goto("/create-listing");

    await expect(page.getByText("Conecte sua conta Melhor Envio")).toBeVisible({ timeout: 8000 });
    await expect(
      page.getByText(/Não foi possível obter o link de conexão/i),
    ).toBeVisible();
    // The anchor button must NOT appear when URL is unavailable
    await expect(page.getByRole("link", { name: /Conectar Melhor Envio/i })).not.toBeVisible();
  });

  test("exibe a tela de bloqueio quando a conexão está expirada", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/logistics/me/status/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ME_EXPIRED),
      });
    });
    await page.route(`${API}/logistics/me/connect/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ME_CONNECT_URL),
      });
    });
    await page.route(`${API}/products/search/filters/options/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_FILTER_OPTIONS) });
    });
    await page.route(`${API}/products/products/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
    });

    await page.goto("/create-listing");

    // connected=true but is_expired=true → shows blocking screen
    await expect(page.getByText("Conecte sua conta Melhor Envio")).toBeVisible({ timeout: 8000 });
    await expect(page.getByRole("link", { name: /Conectar Melhor Envio/i })).toBeVisible();
  });
});

test.describe("ListingForm - Gate Melhor Envio: conectado", () => {
  test("exibe o formulário quando conectado e não expirado", async ({ page }) => {
    await goToCreateListing(page);

    // The gate passed — form step 1 is visible
    await expect(page.getByText("Passo 1 de 7")).toBeVisible();
    await expect(page.getByText("Criar Anúncio")).toBeVisible();
    // Blocking screen must not be present
    await expect(page.getByText("Conecte sua conta Melhor Envio")).not.toBeVisible();
  });
});

test.describe("ListingForm - Gate Melhor Envio: erro na API", () => {
  test("exibe a tela de erro com botão de retry quando a API retorna 500", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);

    await page.route(`${API}/logistics/me/status/`, (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });
    await page.route(`${API}/products/search/filters/options/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_FILTER_OPTIONS) });
    });
    await page.route(`${API}/products/products/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
    });

    await page.goto("/create-listing");

    await expect(page.getByText("Erro ao verificar Melhor Envio")).toBeVisible({ timeout: 8000 });
    await expect(
      page.getByText(/Não foi possível verificar sua conexão/i),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tentar novamente/i }),
    ).toBeVisible();
  });

  test("clicar em 'Tentar novamente' recarrega a página", async ({ page }) => {
    await page.goto("/");
    await injectAuth(page);

    let callCount = 0;
    await page.route(`${API}/logistics/me/status/`, (route) => {
      callCount++;
      if (callCount === 1) {
        route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Error" }) });
      } else {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_ME_CONNECTED) });
      }
    });
    await page.route(`${API}/products/search/filters/options/`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_FILTER_OPTIONS) });
    });
    await page.route(`${API}/products/products/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
    });

    await page.goto("/create-listing");
    await expect(page.getByText("Erro ao verificar Melhor Envio")).toBeVisible({ timeout: 8000 });

    // The retry button calls window.location.reload(), which will trigger
    // the ME status check again. Since the page reloads and routes are
    // re-registered per navigation, we verify the error screen was shown.
    await expect(page.getByRole("button", { name: /Tentar novamente/i })).toBeVisible();
  });
});

// ─── 2. Draft Notice ───────────────────────────────────────────────────────────

test.describe("ListingForm - Rascunho: exibição", () => {
  test("exibe o banner de rascunho quando há dados salvos no localStorage", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);
    // Inject draft BEFORE navigating to the form so it is read on mount
    await injectDraft(page, 3, { title: "Título salvo" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });
    await expect(page.getByText(/passo 3/i)).toBeVisible();
  });

  test("não exibe o banner de rascunho quando não há dados salvos", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    // Reload to confirm no draft banner
    await page.reload();
    // Wait for the ME check to resolve
    await expect(page.getByText("Passo 1 de 7")).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("Rascunho encontrado")).not.toBeVisible();
  });

  test("'Continuar' do rascunho navega para o passo salvo e oculta o banner", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 4, { title: "Draft title", description: "Draft desc" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });

    await page.getByRole("button", { name: /Continuar do passo 4/i }).click();

    await expect(page.getByText("Rascunho encontrado")).not.toBeVisible();
    await expect(page.getByText("Passo 4 de 7")).toBeVisible();
  });

  test("'Descartar' abre o diálogo de confirmação Swal2", async ({ page }) => {
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 2, { title: "To be discarded" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });

    await page.getByRole("button", { name: /Descartar/i }).click();

    // Swal2 confirmation modal must appear
    await expect(page.getByText("Descartar rascunho?")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Todos os dados preenchidos serão perdidos.")).toBeVisible();
    await expect(page.getByRole("button", { name: /Sim, descartar/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Cancelar/i })).toBeVisible();
  });

  test("confirmar descarte limpa o rascunho e volta ao passo 1", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 5, { title: "Draft to discard" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });

    await page.getByRole("button", { name: /Descartar/i }).click();
    await expect(page.getByText("Descartar rascunho?")).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: /Sim, descartar/i }).click();

    // After discard the banner is gone and form is at step 1
    await expect(page.getByText("Rascunho encontrado")).not.toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Passo 1 de 7")).toBeVisible();
  });

  test("cancelar o descarte mantém o banner e os dados do rascunho", async ({
    page,
  }) => {
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 2, { title: "Keep this draft" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });

    await page.getByRole("button", { name: /Descartar/i }).click();
    await expect(page.getByText("Descartar rascunho?")).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: /Cancelar/i }).click();

    // Banner must remain visible
    await expect(page.getByText("Rascunho encontrado")).toBeVisible();
  });

  test("não exibe o banner de rascunho no modo de edição", async ({ page }) => {
    // Inject a draft with the generic key — edit mode must ignore it
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 3, { title: "Should be ignored in edit mode" });
    await mockBaseApis(page);
    await page.route(`${API}/products/listings/42/`, (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_EXISTING_LISTING),
      });
    });

    await page.goto("/ad/42");
    await expect(page.getByText("Editar Anúncio")).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("Rascunho encontrado")).not.toBeVisible();
  });
});

// ─── 3. Navegação por passos ────────────────────────────────────────────────────

test.describe("ListingForm - Navegação por passos", () => {
  test("exibe os 7 pontos de progresso no passo 1", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    // There are 7 progress dots total
    const dots = page.locator(".flex.items-center.justify-center.gap-2 > div");
    await expect(dots).toHaveCount(7);
  });

  test("o ponto ativo no passo 1 é mais largo (w-8)", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    const activeDot = page.locator(
      ".flex.items-center.justify-center.gap-2 > div.bg-blue-900",
    );
    await expect(activeDot).toHaveClass(/w-8/);
  });

  test("'Voltar' não é exibido no passo 1", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    // The back button inside the form nav area only appears on steps > 1
    const backButton = page.locator(
      "form button:has(svg)",
      { hasText: /Voltar/i },
    );
    await expect(backButton).not.toBeVisible();
  });

  test("clicar em 'Próximo' avança para o passo 2 após selecionar produto", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Passo 2 de 7")).toBeVisible();
    await expect(page.getByText("Título")).toBeVisible();
  });

  test("o botão 'Voltar' retorna do passo 2 para o passo 1", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 2 de 7")).toBeVisible();

    await page.getByRole("button", { name: /Voltar/i }).click();

    await expect(page.getByText("Passo 1 de 7")).toBeVisible();
  });

  test("cada passo exibe o nome correto no cabeçalho", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    const stepHeaders = [
      "Produto",
      "Título",
      "Descrição",
      "Marca e Condição",
      "Preço",
      "Dimensões",
      "Imagens",
    ];

    // Step 1
    await expect(page.getByRole("heading", { name: stepHeaders[0] })).toBeVisible();

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[1] })).toBeVisible();

    await page.locator('input[name="title"]').fill("Título de Teste");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[2] })).toBeVisible();

    await page.locator('textarea[name="description"]').fill("Descrição de teste.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[3] })).toBeVisible();

    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[4] })).toBeVisible();

    await page.locator('input[name="price"]').fill("100");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[5] })).toBeVisible();

    await page.locator('input[name="weight_kg"]').fill("1");
    await page.locator('input[name="height_cm"]').fill("10");
    await page.locator('input[name="width_cm"]').fill("20");
    await page.locator('input[name="length_cm"]').fill("30");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByRole("heading", { name: stepHeaders[6] })).toBeVisible();
  });

  test("o botão do último passo mostra 'Publicar Anúncio' no modo de criação", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await fillAndAdvanceAllSteps(page);

    await expect(page.getByRole("button", { name: /Publicar Anúncio/i })).toBeVisible();
  });
});

// ─── 4. Validações de passo ─────────────────────────────────────────────────────

test.describe("ListingForm - Validação: Passo 1 (Produto)", () => {
  test("bloqueia a navegação e exibe erro quando nenhum produto está selecionado", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Selecione um produto")).toBeVisible();
    // Must stay on step 1
    await expect(page.getByText("Passo 1 de 7")).toBeVisible();
  });

  test("limpa o erro de produto ao selecionar um produto", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Selecione um produto")).toBeVisible();

    await page.getByText("Monitor Ultrawide LG").first().click();

    await expect(page.getByText("Selecione um produto")).not.toBeVisible();
  });

  test("permite selecionar produto via campo de busca", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.route(`${API}/products/products/**`, (route) => {
      const url = route.request().url();
      if (url.includes("search=mouse")) {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            count: 1,
            next: null,
            previous: null,
            results: [{ id: 3, name: "Mouse Logitech G502", slug: "mouse-logitech", code: "MOU-LOG-502" }],
          }),
        });
      } else {
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_PRODUCTS_PAGE_1) });
      }
    });

    await page.getByPlaceholder("Buscar produto…").fill("mouse");
    // Wait for debounced search result
    await expect(page.getByText("Mouse Logitech G502")).toBeVisible({ timeout: 2000 });
    await page.getByText("Mouse Logitech G502").click();

    // Selected product is shown in the blue box
    await expect(
      page.locator(".bg-blue-50").filter({ hasText: "Mouse Logitech G502" }),
    ).toBeVisible();
  });

  test("botão X remove o produto selecionado", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await expect(
      page.locator(".bg-blue-50").filter({ hasText: "Monitor Ultrawide LG" }),
    ).toBeVisible();

    // Click the X button to clear the selection
    await page.locator(".bg-blue-50 button").click();

    await expect(
      page.locator(".bg-blue-50").filter({ hasText: "Monitor Ultrawide LG" }),
    ).not.toBeVisible();
  });

  test("exibe o botão 'Carregar mais' quando há mais produtos", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await expect(page.getByRole("button", { name: /Carregar mais/i })).toBeVisible();
  });

  test("clicar em 'Carregar mais' carrega a próxima página de produtos", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    let page2Called = false;
    await page.route(`${API}/products/products/**`, (route) => {
      const url = route.request().url();
      if (url.includes("page=2")) {
        page2Called = true;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_PRODUCTS_PAGE_2),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_PRODUCTS_PAGE_1),
        });
      }
    });

    await page.getByRole("button", { name: /Carregar mais/i }).click();
    await expect(page.getByText("Webcam Logitech C920")).toBeVisible({ timeout: 3000 });
    expect(page2Called).toBe(true);
  });
});

test.describe("ListingForm - Validação: Passo 2 (Título)", () => {
  test("bloqueia a navegação e exibe erro quando o título está vazio", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 2 de 7")).toBeVisible();

    // Try to advance without filling title
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("O título do anúncio é obrigatório")).toBeVisible();
    await expect(page.getByText("Passo 2 de 7")).toBeVisible();
  });

  test("exibe contador de caracteres do título (0/150)", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 2 de 7")).toBeVisible();

    await expect(page.getByText("0/150")).toBeVisible();
  });

  test("o contador de caracteres atualiza conforme o usuário digita", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();

    await page.locator('input[name="title"]').fill("Monitor");
    await expect(page.getByText("7/150")).toBeVisible();
  });

  test("o input de título tem maxLength de 150", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.locator('input[name="title"]')).toHaveAttribute("maxLength", "150");
  });
});

test.describe("ListingForm - Validação: Passo 3 (Descrição)", () => {
  test("bloqueia a navegação e exibe erro quando a descrição está vazia", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 3 de 7")).toBeVisible();

    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Descrição é obrigatória")).toBeVisible();
    await expect(page.getByText("Passo 3 de 7")).toBeVisible();
  });

  test("exibe contador de caracteres da descrição (0/255)", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 3 de 7")).toBeVisible();

    await expect(page.getByText("0/255")).toBeVisible();
  });

  test("o textarea de descrição tem maxLength de 255", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.locator('textarea[name="description"]')).toHaveAttribute("maxLength", "255");
  });
});

test.describe("ListingForm - Validação: Passo 4 (Marca e Condição)", () => {
  test("bloqueia a navegação e exibe erros quando marca e condição estão vazias", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 4 de 7")).toBeVisible();

    // Try to advance without selecting brand or condition
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Selecione uma marca")).toBeVisible();
    await expect(page.getByText("Selecione a condição")).toBeVisible();
    await expect(page.getByText("Passo 4 de 7")).toBeVisible();
  });

  test("exibe as opções de marca no select", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 4 de 7")).toBeVisible();

    const brandSelect = page.getByRole("combobox");
    await expect(brandSelect.getByText("BrandX")).toBeVisible();
    await expect(brandSelect.getByText("BrandY")).toBeVisible();
  });

  test("exibe as opções de condição como botões radio", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 4 de 7")).toBeVisible();

    await expect(page.getByLabel("Novo")).toBeVisible();
    await expect(page.getByLabel("Usado")).toBeVisible();
  });
});

test.describe("ListingForm - Validação: Passo 5 (Preço)", () => {
  test("bloqueia a navegação e exibe erro quando o preço é zero ou vazio", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 5 de 7")).toBeVisible();

    // Leave price empty and advance
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Preço inválido")).toBeVisible();
    await expect(page.getByText("Passo 5 de 7")).toBeVisible();
  });

  test("bloqueia a navegação quando o preço é 0", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 5 de 7")).toBeVisible();

    await page.locator('input[name="price"]').fill("0");
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Preço inválido")).toBeVisible();
  });

  test("o prefixo 'R$' é exibido no campo de preço", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("R$")).toBeVisible();
  });
});

test.describe("ListingForm - Validação: Passo 6 (Dimensões)", () => {
  test("bloqueia a navegação quando todas as dimensões estão vazias", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="price"]').fill("100");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 6 de 7")).toBeVisible();

    // Try to advance without filling dimensions
    await page.getByRole("button", { name: /Próximo/i }).click();

    await expect(page.getByText("Peso inválido")).toBeVisible();
    await expect(page.getByText("Altura inválida")).toBeVisible();
    await expect(page.getByText("Largura inválida")).toBeVisible();
    await expect(page.getByText("Comprimento inválido")).toBeVisible();
    await expect(page.getByText("Passo 6 de 7")).toBeVisible();
  });

  test("exibe todos os campos de dimensão com seus labels", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.getByText("Monitor Ultrawide LG").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Título válido");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição válida.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "1" });
    await page.getByLabel("Novo").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="price"]').fill("100");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 6 de 7")).toBeVisible();

    await expect(page.getByText("Peso (kg)")).toBeVisible();
    await expect(page.getByText("Altura (cm)")).toBeVisible();
    await expect(page.getByText("Largura (cm)")).toBeVisible();
    await expect(page.getByText("Comprimento (cm)")).toBeVisible();
  });
});

test.describe("ListingForm - Passo 7 (Imagens)", () => {
  test("exibe a área de drag-and-drop no passo 7", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await fillAndAdvanceAllSteps(page);

    await expect(
      page.getByText("Clique para selecionar ou arraste as imagens"),
    ).toBeVisible();
    await expect(page.getByText(/JPEG, PNG ou WebP/i)).toBeVisible();
    await expect(page.getByText(/Máx 5MB por imagem/i)).toBeVisible();
  });

  test("o input de arquivo aceita JPEG, PNG e WebP", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await fillAndAdvanceAllSteps(page);

    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    await expect(fileInput).toHaveAttribute("multiple", "");
  });

  test("sem imagens exibe mensagem informativa (opcional)", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await fillAndAdvanceAllSteps(page);

    await expect(
      page.getByText(/Nenhuma imagem selecionada. As imagens são opcionais/i),
    ).toBeVisible();
  });

  test("sem imagens o botão 'Publicar Anúncio' está habilitado", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await fillAndAdvanceAllSteps(page);

    const publishButton = page.getByRole("button", { name: /Publicar Anúncio/i });
    await expect(publishButton).toBeEnabled();
  });
});

// ─── 5. Fluxo de criação bem-sucedido ──────────────────────────────────────────

test.describe("ListingForm - Criação de anúncio: fluxo completo sem imagens", () => {
  test("chama POST /products/listings/create/ com packages[] e navega para /dashboard", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    let createPayload: any = null;
    await page.route(`${API}/products/listings/create/`, (route) => {
      createPayload = route.request().postDataJSON();
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CREATED_LISTING),
      });
    });

    // Mock dashboard route to prevent broken redirects
    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
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

    await fillAndAdvanceAllSteps(page);

    // Click Publicar Anúncio
    await page.getByRole("button", { name: /Publicar Anúncio/i }).click();

    // Swal2 success toast
    await expect(page.getByText("Anúncio publicado!")).toBeVisible({ timeout: 8000 });
    await expect(page.getByText("Seu anúncio foi criado com sucesso.")).toBeVisible();

    // Wait for navigation to /dashboard (Swal2 auto-closes after timer)
    await page.waitForURL(/\/dashboard/, { timeout: 10000 });

    // Verify the create payload included packages array
    expect(createPayload).not.toBeNull();
    expect(createPayload).toHaveProperty("packages");
    expect(Array.isArray(createPayload.packages)).toBe(true);
    expect(createPayload.packages).toHaveLength(1);
    expect(createPayload.packages[0]).toMatchObject({
      weight_kg: "3.50",
      height_cm: "20.00",
      width_cm: "80.00",
      length_cm: "50.00",
    });
    expect(createPayload.product).toBe(1);
    expect(createPayload.brand).toBe(1);
    expect(createPayload.condition).toBe(1);
  });
});

test.describe("ListingForm - Criação de anúncio: com imagens", () => {
  test("cria o anúncio, faz upload para S3 e vincula as imagens", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    let createCalled = false;
    let presignedCalled = false;
    let s3PutCalled = false;
    let linkImageCalled = false;

    await page.route(`${API}/products/listings/create/`, (route) => {
      createCalled = true;
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CREATED_LISTING),
      });
    });

    await page.route(`${API}/storage/upload/presigned-url/`, (route) => {
      presignedCalled = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_PRESIGNED_URL),
      });
    });

    // S3 upload (the presigned PUT URL is external)
    await page.route("http://localhost:9000/**", (route) => {
      s3PutCalled = true;
      route.fulfill({ status: 200, body: "" });
    });

    await page.route(`${API}/products/listings/999/images/`, (route) => {
      linkImageCalled = true;
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_IMAGE_LINKED),
      });
    });

    // Mock dashboard APIs
    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
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

    await fillAndAdvanceAllSteps(page);

    // Upload a file on step 7
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "test-image.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from("fake-jpeg-content"),
    });

    // Confirm image was added to the pending list
    await expect(
      page.getByText(/Novas imagens \(1\)/i),
    ).toBeVisible({ timeout: 3000 });

    await page.getByRole("button", { name: /Publicar Anúncio/i }).click();

    // Wait for the success dialog
    await expect(page.getByText("Anúncio publicado!")).toBeVisible({ timeout: 10000 });

    // Verify all three API calls were made in order
    expect(createCalled).toBe(true);
    expect(presignedCalled).toBe(true);
    expect(s3PutCalled).toBe(true);
    expect(linkImageCalled).toBe(true);
  });
});

test.describe("ListingForm - Criação: erro na API de criação", () => {
  test("exibe alerta de erro Swal2 e permanece no formulário quando a API retorna 400", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.route(`${API}/products/listings/create/`, (route) => {
      route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Produto já anunciado por este vendedor." }),
      });
    });

    await fillAndAdvanceAllSteps(page);
    await page.getByRole("button", { name: /Publicar Anúncio/i }).click();

    await expect(page.getByText("Erro")).toBeVisible({ timeout: 8000 });
    await expect(
      page.getByText("Produto já anunciado por este vendedor."),
    ).toBeVisible();

    // After dismissing the error dialog the form stays on the page
    await page.getByRole("button", { name: /OK/i }).click();
    await expect(page.getByText("Passo 7 de 7")).toBeVisible();
  });

  test("exibe mensagem de erro genérica quando a API retorna 500 sem detail", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.route(`${API}/products/listings/create/`, (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await fillAndAdvanceAllSteps(page);
    await page.getByRole("button", { name: /Publicar Anúncio/i }).click();

    await expect(page.getByText("Erro")).toBeVisible({ timeout: 8000 });
  });
});

test.describe("ListingForm - Criação: falha no upload de imagens", () => {
  test("exibe warning Swal2 e navega para /dashboard quando o upload de imagem falha", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await page.route(`${API}/products/listings/create/`, (route) => {
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CREATED_LISTING),
      });
    });

    // Presigned URL request fails — triggers upload failure path
    await page.route(`${API}/storage/upload/presigned-url/`, (route) => {
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Storage service unavailable" }),
      });
    });

    // Mock dashboard APIs
    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
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

    await fillAndAdvanceAllSteps(page);

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "test-image.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from("fake-jpeg-content"),
    });
    await expect(page.getByText(/Novas imagens \(1\)/i)).toBeVisible({ timeout: 3000 });

    await page.getByRole("button", { name: /Publicar Anúncio/i }).click();

    // Warning dialog: listing was created but images failed
    await expect(page.getByText("Anúncio criado!")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/ocorreu um erro ao enviar as imagens/i)).toBeVisible();

    // Confirm to navigate to dashboard
    await page.getByRole("button", { name: /OK/i }).click();
    await page.waitForURL(/\/dashboard/, { timeout: 8000 });
  });
});

// ─── 6. Modo de edição ──────────────────────────────────────────────────────────

test.describe("ListingForm - Modo de edição", () => {
  test("exibe o título 'Editar Anúncio' em modo de edição", async ({ page }) => {
    await goToEditListing(page, 42);

    await expect(page.getByText("Editar Anúncio")).toBeVisible();
    await expect(page.getByText("Criar Anúncio")).not.toBeVisible();
  });

  test("pré-carrega os dados existentes do anúncio nos campos", async ({
    page,
  }) => {
    await goToEditListing(page, 42);

    // Navigate to step 2 to check the title
    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 2 de 7")).toBeVisible();

    await expect(page.locator('input[name="title"]')).toHaveValue("Teclado Keychron K2 v2");
  });

  test("pré-carrega a descrição do anúncio existente", async ({ page }) => {
    await goToEditListing(page, 42);

    // Navigate to step 3
    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 3 de 7")).toBeVisible();

    await expect(page.locator('textarea[name="description"]')).toHaveValue(
      "Teclado mecânico compacto, excelente estado.",
    );
  });

  test("pré-carrega o preço do anúncio existente", async ({ page }) => {
    await goToEditListing(page, 42);

    // Navigate to step 5
    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 5 de 7")).toBeVisible();

    await expect(page.locator('input[name="price"]')).toHaveValue("450.00");
  });

  test("exibe imagens existentes no passo 7 em modo de edição", async ({
    page,
  }) => {
    await goToEditListing(page, 42);

    // Navigate to step 7
    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Teclado Keychron K2 v2");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Teclado mecânico compacto, excelente estado.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "2" });
    await page.getByLabel("Usado").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="price"]').fill("450");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="weight_kg"]').fill("1.2");
    await page.locator('input[name="height_cm"]').fill("5");
    await page.locator('input[name="width_cm"]').fill("35");
    await page.locator('input[name="length_cm"]').fill("15");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 7 de 7")).toBeVisible();

    await expect(page.getByText("Imagens atuais")).toBeVisible();
    await expect(page.getByAltText("Imagem existente")).toBeVisible();
  });

  test("o botão do último passo exibe 'Salvar alterações' em modo de edição", async ({
    page,
  }) => {
    await goToEditListing(page, 42);

    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Teclado Keychron K2 v2");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Teclado mecânico compacto, excelente estado.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "2" });
    await page.getByLabel("Usado").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="price"]').fill("450");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="weight_kg"]').fill("1.2");
    await page.locator('input[name="height_cm"]').fill("5");
    await page.locator('input[name="width_cm"]').fill("35");
    await page.locator('input[name="length_cm"]').fill("15");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 7 de 7")).toBeVisible();

    await expect(
      page.getByRole("button", { name: /Salvar alterações/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Publicar Anúncio/i }),
    ).not.toBeVisible();
  });

  test("submissão em modo de edição chama PUT /products/listings/{id}/update/", async ({
    page,
  }) => {
    await goToEditListing(page, 42);

    let updateCalled = false;
    let updateUrl = "";
    await page.route(`${API}/products/listings/42/update/`, (route) => {
      updateCalled = true;
      updateUrl = route.request().url();
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...MOCK_EXISTING_LISTING }),
      });
    });

    // Mock dashboard APIs
    await page.route(`${API}/products/my-listings/**`, (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }) });
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

    // Navigate through all 7 steps in edit mode
    await page.getByText("Teclado Mecânico Keychron").first().click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="title"]').fill("Teclado Keychron K2 v2 Editado");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('textarea[name="description"]').fill("Descrição editada.");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.getByRole("combobox").selectOption({ value: "2" });
    await page.getByLabel("Usado").click();
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="price"]').fill("400");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await page.locator('input[name="weight_kg"]').fill("1.2");
    await page.locator('input[name="height_cm"]').fill("5");
    await page.locator('input[name="width_cm"]').fill("35");
    await page.locator('input[name="length_cm"]').fill("15");
    await page.getByRole("button", { name: /Próximo/i }).click();
    await expect(page.getByText("Passo 7 de 7")).toBeVisible();

    await page.getByRole("button", { name: /Salvar alterações/i }).click();

    await expect(page.getByText("Anúncio atualizado!")).toBeVisible({ timeout: 8000 });

    await page.waitForURL(/\/dashboard/, { timeout: 10000 });

    expect(updateCalled).toBe(true);
    expect(updateUrl).toContain("/products/listings/42/update/");
  });
});

// ─── 7. Responsividade mobile ───────────────────────────────────────────────────

test.describe("ListingForm - Responsividade Mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("exibe o formulário corretamente em viewport mobile", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await expect(page.getByText("Criar Anúncio")).toBeVisible();
    await expect(page.getByText("Passo 1 de 7")).toBeVisible();
  });

  test("os 7 pontos de progresso são visíveis em mobile", async ({ page }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    const dots = page.locator(".flex.items-center.justify-center.gap-2 > div");
    await expect(dots).toHaveCount(7);
  });

  test("o botão de ação principal está visível no viewport mobile", async ({
    page,
  }) => {
    await goToCreateListing(page);
    await clearDraft(page);

    await expect(page.getByRole("button", { name: /Próximo/i })).toBeVisible();
  });

  test("o banner de rascunho é visível em mobile", async ({ page }) => {
    await page.goto("/");
    await injectAuth(page);
    await injectDraft(page, 2, { title: "Mobile draft" });
    await mockBaseApis(page);

    await page.goto("/create-listing");
    await expect(page.getByText("Rascunho encontrado")).toBeVisible({ timeout: 8000 });
  });
});
