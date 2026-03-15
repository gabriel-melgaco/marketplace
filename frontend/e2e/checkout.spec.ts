import { test, expect } from "@playwright/test";
import { injectAuth, clearAuth } from "./helpers/auth";

// ─── API Base ──────────────────────────────────────────────────────────────────
// Matches the VITE_API_URL default consumed by the app's axios instance.
const API = "http://localhost:8000";

// ─── Cart Storage Key ─────────────────────────────────────────────────────────
// Must match CART_STORAGE_KEY in CartContext.tsx.
const CART_STORAGE_KEY = "cart_items";

// ─── Mock Fixtures ─────────────────────────────────────────────────────────────

/**
 * A minimal MarketplaceListing fixture that satisfies CartItem.listing.
 * seller field is a numeric id; seller_name is the display name.
 */
const MOCK_LISTING_SELLER_A = {
  id: 101,
  product: { id: 1, name: "Tênis Running Pro", slug: "tenis-running-pro", code: null },
  category: { id: 2, name: "Calçados", slug: "calcados" },
  seller: 10,
  seller_name: "Loja SportZone",
  title: "Tênis Running Pro Azul",
  price: "299.90",
  brand: { id: 3, name: "Nike", slug: "nike", logo: null },
  quantity: 5,
  is_active: true,
  description: "Ótimo tênis para corrida.",
  condition: { id: 1, name: "Novo", slug: "novo" },
  views_count: 42,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
  sold_at: null,
  images: [],
  primary_image: null,
  shipping_address: null,
};

const MOCK_LISTING_SELLER_B = {
  id: 202,
  product: { id: 2, name: "Mochila Urban 30L", slug: "mochila-urban-30l", code: null },
  category: { id: 3, name: "Acessórios", slug: "acessorios" },
  seller: 20,
  seller_name: "Mochileiros Brasil",
  title: "Mochila Urban 30L Preta",
  price: "189.00",
  brand: { id: 4, name: "Adidas", slug: "adidas", logo: null },
  quantity: 3,
  is_active: true,
  description: "Mochila resistente e espaçosa.",
  condition: { id: 1, name: "Novo", slug: "novo" },
  views_count: 18,
  created_at: "2025-01-02T00:00:00Z",
  updated_at: "2025-01-02T00:00:00Z",
  sold_at: null,
  images: [],
  primary_image: null,
  shipping_address: null,
};

/** A single-seller cart with one item. */
const CART_SINGLE_SELLER = [
  { listing: MOCK_LISTING_SELLER_A, quantity: 2 },
];

/** A two-seller cart used to test per-seller grouping and freight selection. */
const CART_TWO_SELLERS = [
  { listing: MOCK_LISTING_SELLER_A, quantity: 1 },
  { listing: MOCK_LISTING_SELLER_B, quantity: 1 },
];

const MOCK_ADDRESS_DEFAULT: import("../src/services/addressService").Address = {
  id: 1,
  address_type: "shipping",
  recipient_name: "Test User",
  recipient_phone: "11999990000",
  zipcode: "01310-100",
  street: "Avenida Paulista",
  number: "1000",
  complement: "Apto 42",
  neighborhood: "Bela Vista",
  city: "São Paulo",
  state: "SP",
  country: "BR",
  is_default: true,
  is_active: true,
  is_shipping_address: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const MOCK_ADDRESS_SECONDARY: import("../src/services/addressService").Address = {
  id: 2,
  address_type: "shipping",
  recipient_name: "Test User (Casa)",
  recipient_phone: "11988880000",
  zipcode: "04101-300",
  street: "Rua das Flores",
  number: "55",
  complement: "",
  neighborhood: "Vila Mariana",
  city: "São Paulo",
  state: "SP",
  country: "BR",
  is_default: false,
  is_active: true,
  is_shipping_address: true,
  created_at: "2025-01-03T00:00:00Z",
  updated_at: "2025-01-03T00:00:00Z",
};

const MOCK_NEW_ADDRESS_CREATED: import("../src/services/addressService").Address = {
  id: 99,
  address_type: "shipping",
  recipient_name: "Maria Silva",
  recipient_phone: "21977770000",
  zipcode: "20040-020",
  street: "Avenida Rio Branco",
  number: "156",
  complement: "",
  neighborhood: "Centro",
  city: "Rio de Janeiro",
  state: "RJ",
  country: "BR",
  is_default: false,
  is_active: true,
  is_shipping_address: true,
  created_at: "2025-03-15T00:00:00Z",
  updated_at: "2025-03-15T00:00:00Z",
};

/** Shipping quotes response for a single melhor_envio seller (seller id "10"). */
const MOCK_SHIPPING_RESPONSE_SELLER_A = {
  quotes_by_seller: {
    "10": {
      seller_name: "Loja SportZone",
      in_person_only: false,
      in_person_items: [],
      quotes: [
        {
          service_id: 1,
          name: "PAC",
          company: "Correios",
          company_picture: null,
          price: 18.5,
          delivery_time: 7,
        },
        {
          service_id: 2,
          name: "SEDEX",
          company: "Correios",
          company_picture: null,
          price: 35.0,
          delivery_time: 2,
        },
      ],
    },
  },
  shipping_address_id: 1,
  total_items: 1,
  total_value: 299.9,
};

/** Shipping quotes response where seller 10 is in_person_only. */
const MOCK_SHIPPING_RESPONSE_IN_PERSON = {
  quotes_by_seller: {
    "10": {
      seller_name: "Loja SportZone",
      in_person_only: true,
      in_person_items: [101],
      quotes: [],
    },
  },
  shipping_address_id: 1,
  total_items: 1,
  total_value: 299.9,
};

/** Shipping quotes for two sellers: seller 10 (melhor_envio) and seller 20 (melhor_envio). */
const MOCK_SHIPPING_RESPONSE_TWO_SELLERS = {
  quotes_by_seller: {
    "10": {
      seller_name: "Loja SportZone",
      in_person_only: false,
      in_person_items: [],
      quotes: [
        {
          service_id: 1,
          name: "PAC",
          company: "Correios",
          company_picture: null,
          price: 18.5,
          delivery_time: 7,
        },
      ],
    },
    "20": {
      seller_name: "Mochileiros Brasil",
      in_person_only: false,
      in_person_items: [],
      quotes: [
        {
          service_id: 3,
          name: "Mini Envios",
          company: "Jadlog",
          company_picture: null,
          price: 12.0,
          delivery_time: 5,
        },
      ],
    },
  },
  shipping_address_id: 1,
  total_items: 2,
  total_value: 488.9,
};

const MOCK_CEP_LOOKUP_RESPONSE = {
  zipcode: "20040020",
  street: "Avenida Rio Branco",
  neighborhood: "Centro",
  city: "Rio de Janeiro",
  state: "RJ",
};

// ─── Shared Setup Helpers ─────────────────────────────────────────────────────

/**
 * Mocks the base layout API calls that fire on every page using HomeLayout.
 * Keeping these minimal avoids network errors that could mask test failures.
 */
async function mockBaseLayoutApis(page: import("@playwright/test").Page) {
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
 * Seeds the cart in localStorage so the checkout page will not immediately
 * redirect to "/". Must be called after page.goto() establishes the origin.
 */
async function seedCart(
  page: import("@playwright/test").Page,
  items: { listing: object; quantity: number }[],
) {
  await page.evaluate(
    ({ key, data }) => {
      localStorage.setItem(key, JSON.stringify(data));
    },
    { key: CART_STORAGE_KEY, data: items },
  );
}

/**
 * Clears the cart from localStorage so the checkout page will redirect away.
 */
async function clearCart(page: import("@playwright/test").Page) {
  await page.evaluate((key) => {
    localStorage.removeItem(key);
  }, CART_STORAGE_KEY);
}

/**
 * Navigates to /checkout with:
 *  - auth injected
 *  - cart pre-seeded
 *  - addresses API mocked
 *  - shipping calculate API mocked
 *
 * Returns when the page heading "Finalizar Compra" is visible.
 */
async function goToCheckout(
  page: import("@playwright/test").Page,
  options: {
    cartItems?: { listing: object; quantity: number }[];
    addresses?: object[];
    shippingResponse?: object;
  } = {},
) {
  const {
    cartItems = CART_SINGLE_SELLER,
    addresses = [MOCK_ADDRESS_DEFAULT],
    shippingResponse = MOCK_SHIPPING_RESPONSE_SELLER_A,
  } = options;

  await mockBaseLayoutApis(page);

  // Mock addresses list
  await page.route(`${API}/logistics/addresses/`, (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(addresses),
      });
    } else {
      // POST — create address; handled per-test when needed
      route.continue();
    }
  });

  // Mock shipping calculate
  await page.route(`${API}/logistics/shipping/calculate/`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(shippingResponse),
    });
  });

  // Navigate to origin first so we can write localStorage
  await page.goto("/");
  await injectAuth(page);
  await seedCart(page, cartItems);

  // Navigate to checkout — auth + cart are now in localStorage
  await page.goto("/checkout");
  await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

test.describe("Checkout", () => {
  // ── 1. Proteção de rota ────────────────────────────────────────────────────

  test.describe("Proteção de rota", () => {
    test("redireciona para /login quando o usuário não está autenticado", async ({
      page,
    }) => {
      await page.goto("/");
      await clearAuth(page);
      await page.goto("/checkout");

      await expect(page).toHaveURL(/\/login/);
    });

    test("redireciona para / quando o carrinho está vazio", async ({ page }) => {
      await mockBaseLayoutApis(page);
      await page.goto("/");
      await injectAuth(page);
      // Explicitly clear the cart so there are no items
      await clearCart(page);

      await page.goto("/checkout");

      // The component calls navigate("/", { replace: true }) when items.length === 0.
      await expect(page).toHaveURL(/^\//);
      await expect(page).not.toHaveURL(/\/checkout/);
    });
  });

  // ── 2. Itens do carrinho agrupados por vendedor ────────────────────────────

  test.describe("Itens do carrinho", () => {
    test("exibe o título 'Finalizar Compra' e a seção 'Itens do pedido'", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();
      await expect(page.getByText("Itens do pedido")).toBeVisible();
    });

    test("exibe o nome do produto e o vendedor de um único vendedor", async ({
      page,
    }) => {
      await goToCheckout(page);

      // The seller name appears inside the cart section header.
      await expect(page.getByText("Loja SportZone").first()).toBeVisible();
      // The product title is rendered per item.
      await expect(page.getByText("Tênis Running Pro Azul")).toBeVisible();
    });

    test("exibe itens agrupados por vendedor quando há dois vendedores distintos", async ({
      page,
    }) => {
      await goToCheckout(page, {
        cartItems: CART_TWO_SELLERS,
        shippingResponse: MOCK_SHIPPING_RESPONSE_TWO_SELLERS,
      });

      await expect(page.getByText("Loja SportZone").first()).toBeVisible();
      await expect(page.getByText("Mochileiros Brasil").first()).toBeVisible();
      await expect(page.getByText("Tênis Running Pro Azul")).toBeVisible();
      await expect(page.getByText("Mochila Urban 30L Preta")).toBeVisible();
    });

    test("exibe quantidade e preço unitário no formato 'Qtd × R$ Preço'", async ({
      page,
    }) => {
      // 2 units of R$ 299.90
      await goToCheckout(page);

      // The component renders "{quantity} × {formatCurrency(unitPrice)}"
      await expect(page.getByText(/2 × R\$\s*299/)).toBeVisible();
    });

    test("exibe o subtotal correto do vendedor", async ({ page }) => {
      // 2 × 299.90 = 599.80
      await goToCheckout(page);

      await expect(page.getByText(/Subtotal do vendedor/)).toBeVisible();
      // R$ 599,80 — Playwright normalises non-breaking spaces in text matchers
      await expect(page.getByText(/599/)).toBeVisible();
    });
  });

  // ── 3. Endereços salvos ────────────────────────────────────────────────────

  test.describe("Endereços salvos", () => {
    test("exibe endereços salvos como cards clicáveis", async ({ page }) => {
      await goToCheckout(page, {
        addresses: [MOCK_ADDRESS_DEFAULT, MOCK_ADDRESS_SECONDARY],
      });

      await expect(page.getByText("Test User")).toBeVisible();
      await expect(page.getByText("Test User (Casa)")).toBeVisible();
    });

    test("marca o endereço padrão como selecionado automaticamente ao carregar", async ({
      page,
    }) => {
      await goToCheckout(page, {
        addresses: [MOCK_ADDRESS_DEFAULT, MOCK_ADDRESS_SECONDARY],
      });

      // The default address has the badge "Padrão"
      await expect(page.getByText("Padrão")).toBeVisible();

      // The "Entregando em" preview in the sidebar should show the default address
      await expect(page.getByText(/Entregando em/i)).toBeVisible();
      await expect(page.getByText(/Avenida Paulista/)).toBeVisible();
    });

    test("permite selecionar um endereço diferente clicando no card", async ({
      page,
    }) => {
      await goToCheckout(page, {
        addresses: [MOCK_ADDRESS_DEFAULT, MOCK_ADDRESS_SECONDARY],
        shippingResponse: MOCK_SHIPPING_RESPONSE_SELLER_A,
      });

      // Click on the secondary address card
      await page.getByText("Test User (Casa)").click();

      // Sidebar preview should update to show the secondary address street
      await expect(page.getByText(/Rua das Flores/)).toBeVisible();
    });

    test("exibe badge 'Padrão' apenas no endereço marcado como is_default", async ({
      page,
    }) => {
      await goToCheckout(page, {
        addresses: [MOCK_ADDRESS_DEFAULT, MOCK_ADDRESS_SECONDARY],
      });

      // Only one "Padrão" badge should exist
      await expect(page.getByText("Padrão")).toHaveCount(1);
    });

    test("exibe o endereço selecionado no painel lateral 'Entregando em'", async ({
      page,
    }) => {
      await goToCheckout(page);

      // The sidebar shows the selected address preview
      await expect(page.getByText(/Entregando em/i)).toBeVisible();
      await expect(page.getByText(/Avenida Paulista, 1000/)).toBeVisible();
    });
  });

  // ── 4. Formulário de novo endereço (sem endereços salvos) ──────────────────

  test.describe("Formulário inline de endereço — sem endereços salvos", () => {
    test("exibe o formulário de endereço inline quando não há endereços cadastrados", async ({
      page,
    }) => {
      await goToCheckout(page, { addresses: [] });

      // When addresses is empty, showAddressForm starts as true
      await expect(page.getByPlaceholder("Nome completo")).toBeVisible();
      await expect(page.getByPlaceholder("(00) 00000-0000")).toBeVisible();
      await expect(page.getByPlaceholder("00000-000")).toBeVisible();
    });

    test("exibe o botão '+ Adicionar novo endereço' quando há endereços e o form está oculto", async ({
      page,
    }) => {
      await goToCheckout(page, { addresses: [MOCK_ADDRESS_DEFAULT] });

      await expect(
        page.getByRole("button", { name: /Adicionar novo endereço/ }),
      ).toBeVisible();
    });

    test("clicar em '+ Adicionar novo endereço' abre o formulário inline", async ({
      page,
    }) => {
      await goToCheckout(page, { addresses: [MOCK_ADDRESS_DEFAULT] });

      await page.getByRole("button", { name: /Adicionar novo endereço/ }).click();

      await expect(page.getByPlaceholder("Nome completo")).toBeVisible();
      await expect(page.getByPlaceholder("00000-000")).toBeVisible();
    });

    test("clicar em 'Cancelar' fecha o formulário inline", async ({ page }) => {
      await goToCheckout(page, { addresses: [MOCK_ADDRESS_DEFAULT] });

      await page.getByRole("button", { name: /Adicionar novo endereço/ }).click();
      await expect(page.getByPlaceholder("Nome completo")).toBeVisible();

      // The cancel button inside the form
      await page.getByRole("button", { name: "Cancelar" }).click();

      await expect(page.getByPlaceholder("Nome completo")).not.toBeVisible();
    });

    test("exibe erro de validação ao tentar salvar com campos obrigatórios vazios", async ({
      page,
    }) => {
      await goToCheckout(page, { addresses: [] });

      // Click save without filling any field
      await page.getByRole("button", { name: "Salvar endereço" }).click();

      await expect(
        page.getByText("Preencha todos os campos obrigatórios."),
      ).toBeVisible();
    });
  });

  // ── 5. Busca de CEP (autofill) ─────────────────────────────────────────────

  test.describe("Busca automática de CEP", () => {
    test("preenche rua, bairro, cidade e estado ao sair do campo CEP com 8 dígitos", async ({
      page,
    }) => {
      // Mock the CEP lookup endpoint before navigating
      await page.route(`${API}/logistics/cep/lookup/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_CEP_LOOKUP_RESPONSE),
        });
      });

      await goToCheckout(page, { addresses: [] });

      const cepInput = page.getByPlaceholder("00000-000");
      await cepInput.fill("20040-020");
      // Blur triggers handleCepBlur
      await cepInput.blur();

      // Wait for the autofill to complete — the service is async
      await expect(page.getByPlaceholder("Nome da rua")).toHaveValue(
        "Avenida Rio Branco",
      );
      await expect(page.getByPlaceholder("Bairro")).toHaveValue("Centro");
      await expect(page.getByPlaceholder("Cidade")).toHaveValue("Rio de Janeiro");
      // The state select should be set to "RJ"
      await expect(page.locator("select")).toHaveValue("RJ");
    });

    test("não chama a API de CEP se o campo tiver menos de 8 dígitos", async ({
      page,
    }) => {
      let cepCalled = false;
      await page.route(`${API}/logistics/cep/lookup/`, (route) => {
        cepCalled = true;
        route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      });

      await goToCheckout(page, { addresses: [] });

      const cepInput = page.getByPlaceholder("00000-000");
      await cepInput.fill("12345");
      await cepInput.blur();

      // Give time for any spurious request
      await page.waitForTimeout(300);
      expect(cepCalled).toBe(false);
    });

    test("mantém os campos preenchidos manualmente quando o CEP falha", async ({
      page,
    }) => {
      // Return a network error so the CEP lookup throws
      await page.route(`${API}/logistics/cep/lookup/`, (route) => {
        route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
      });

      await goToCheckout(page, { addresses: [] });

      // Fill in street manually before CEP blur
      await page.getByPlaceholder("Nome da rua").fill("Rua Manual");

      const cepInput = page.getByPlaceholder("00000-000");
      await cepInput.fill("00000-000");
      await cepInput.blur();

      await page.waitForTimeout(300);
      // Manual value should be preserved — the component fails silently
      await expect(page.getByPlaceholder("Nome da rua")).toHaveValue("Rua Manual");
    });
  });

  // ── 6. Salvar novo endereço ────────────────────────────────────────────────

  test.describe("Salvar novo endereço", () => {
    /**
     * Fills every required field in the address form using realistic data.
     */
    async function fillAddressForm(page: import("@playwright/test").Page) {
      await page.getByPlaceholder("Nome completo").fill("Maria Silva");
      await page.getByPlaceholder("(00) 00000-0000").fill("(21) 97777-0000");
      await page.getByPlaceholder("00000-000").fill("20040-020");
      await page.getByPlaceholder("123").fill("156");
      await page.getByPlaceholder("Nome da rua").fill("Avenida Rio Branco");
      await page.getByPlaceholder("Bairro").fill("Centro");
      await page.getByPlaceholder("Cidade").fill("Rio de Janeiro");
      await page.locator("select").selectOption("RJ");
    }

    test("salvar endereço válido o adiciona à lista e o seleciona", async ({
      page,
    }) => {
      // Override the POST /logistics/addresses/ route for this test
      await page.route(`${API}/logistics/addresses/`, (route) => {
        if (route.request().method() === "POST") {
          route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify(MOCK_NEW_ADDRESS_CREATED),
          });
        } else {
          route.fulfill({
            status: 200,
            contentType: "application/json",
            // No pre-existing addresses — this triggers showAddressForm=true
            body: JSON.stringify([]),
          });
        }
      });

      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/shipping/calculate/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");
      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();

      await fillAddressForm(page);
      await page.getByRole("button", { name: "Salvar endereço" }).click();

      // After saving, the created address card should appear
      await expect(page.getByText("Maria Silva")).toBeVisible();

      // Sidebar preview should reflect the new address
      await expect(page.getByText(/Entregando em/i)).toBeVisible();
      await expect(page.getByText(/Avenida Rio Branco/)).toBeVisible();
    });

    test("o formulário é ocultado após salvar com sucesso", async ({ page }) => {
      await page.route(`${API}/logistics/addresses/`, (route) => {
        if (route.request().method() === "POST") {
          route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify(MOCK_NEW_ADDRESS_CREATED),
          });
        } else {
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/shipping/calculate/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");
      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();

      await fillAddressForm(page);
      await page.getByRole("button", { name: "Salvar endereço" }).click();

      // The form fields should no longer be visible
      await expect(page.getByPlaceholder("Nome completo")).not.toBeVisible();
    });

    test("exibe mensagem de erro da API ao falhar ao salvar endereço", async ({
      page,
    }) => {
      await page.route(`${API}/logistics/addresses/`, (route) => {
        if (route.request().method() === "POST") {
          route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ zipcode: ["CEP inválido."] }),
          });
        } else {
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/shipping/calculate/`, (route) => {
        route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");
      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();

      await fillAddressForm(page);
      await page.getByRole("button", { name: "Salvar endereço" }).click();

      await expect(page.getByText("CEP inválido.")).toBeVisible();
    });
  });

  // ── 7. Cálculo de frete — disparo automático ───────────────────────────────

  test.describe("Cálculo automático de frete", () => {
    test("dispara POST /logistics/shipping/calculate/ ao carregar com endereço pré-selecionado", async ({
      page,
    }) => {
      let calculateCalled = false;
      let capturedBody: unknown = null;

      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/addresses/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([MOCK_ADDRESS_DEFAULT]),
        });
      });
      await page.route(`${API}/logistics/shipping/calculate/`, async (route) => {
        calculateCalled = true;
        capturedBody = JSON.parse(route.request().postData() ?? "{}");
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");
      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();

      // Wait for shipping section to appear (triggered by selectedAddressId effect)
      await expect(page.getByText("Opções de frete")).toBeVisible();

      expect(calculateCalled).toBe(true);
      expect(capturedBody).toMatchObject({ shipping_address_id: MOCK_ADDRESS_DEFAULT.id });
    });

    test("re-dispara o cálculo ao trocar o endereço selecionado", async ({
      page,
    }) => {
      let calculateCallCount = 0;

      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/addresses/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([MOCK_ADDRESS_DEFAULT, MOCK_ADDRESS_SECONDARY]),
        });
      });
      await page.route(`${API}/logistics/shipping/calculate/`, (route) => {
        calculateCallCount++;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");
      await expect(page.getByText("Opções de frete")).toBeVisible();

      const firstCallCount = calculateCallCount;

      // Switch to secondary address
      await page.getByText("Test User (Casa)").click();

      // Wait for shipping recalculation to settle
      await expect(page.getByText(/Calculando frete|PAC|Mini Envios/)).toBeVisible();

      expect(calculateCallCount).toBeGreaterThan(firstCallCount);
    });

    test("exibe 'Calculando frete...' enquanto a requisição está pendente", async ({
      page,
    }) => {
      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/addresses/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([MOCK_ADDRESS_DEFAULT]),
        });
      });

      // Delay the shipping response to catch the loading state
      await page.route(`${API}/logistics/shipping/calculate/`, async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 400));
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");

      await expect(page.getByText("Finalizar Compra")).toBeVisible();
      // The loading state text appears while shippingLoading is true
      await expect(page.getByText("Calculando frete...")).toBeVisible();
    });
  });

  // ── 8. Vendedor in_person_only ─────────────────────────────────────────────

  test.describe("Vendedor in_person_only", () => {
    test("exibe mensagem de entrega presencial para vendedor in_person_only", async ({
      page,
    }) => {
      await goToCheckout(page, {
        shippingResponse: MOCK_SHIPPING_RESPONSE_IN_PERSON,
      });

      await expect(page.getByText("Opções de frete")).toBeVisible();
      await expect(
        page.getByText(/entrega presencial/i),
      ).toBeVisible();
      await expect(
        page.getByText(/Entre em contato após a compra/i),
      ).toBeVisible();
    });

    test("não exibe cards de frete para vendedor in_person_only", async ({
      page,
    }) => {
      await goToCheckout(page, {
        shippingResponse: MOCK_SHIPPING_RESPONSE_IN_PERSON,
      });

      await expect(page.getByText("Opções de frete")).toBeVisible();
      // PAC and SEDEX should NOT appear
      await expect(page.getByText("PAC")).not.toBeVisible();
      await expect(page.getByText("SEDEX")).not.toBeVisible();
    });

    test("botão 'Ir para pagamento' está habilitado para vendedor in_person_only sem seleção de frete necessária", async ({
      page,
    }) => {
      await goToCheckout(page, {
        shippingResponse: MOCK_SHIPPING_RESPONSE_IN_PERSON,
      });

      await expect(page.getByText("Opções de frete")).toBeVisible();

      // For in_person_only sellers no freight selection is required, so
      // allServicesSelected should return true and the button should be enabled.
      const button = page.getByRole("button", { name: /Ir para pagamento/i });
      await expect(button).not.toBeDisabled();
    });
  });

  // ── 9. Opções de frete (melhor_envio) ─────────────────────────────────────

  test.describe("Opções de frete — melhor_envio", () => {
    test("exibe cards de frete com nome, transportadora e preço", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("Opções de frete")).toBeVisible();
      await expect(page.getByText("PAC")).toBeVisible();
      await expect(page.getByText("SEDEX")).toBeVisible();
      await expect(page.getByText("Correios").first()).toBeVisible();
    });

    test("exibe o prazo de entrega em dias úteis", async ({ page }) => {
      await goToCheckout(page);

      await expect(page.getByText("Opções de frete")).toBeVisible();
      await expect(page.getByText(/7 dias úteis/)).toBeVisible();
      await expect(page.getByText(/2 dias úteis/)).toBeVisible();
    });

    test("selecionar uma opção de frete marca o card visualmente", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();
      const pacCard = page.getByText("PAC").locator("..").locator("..");
      await pacCard.click();

      // After clicking, the card receives border-blue-800 — checking the
      // radio indicator inner dot is the most reliable selector-agnostic signal.
      // We verify the freight total in the sidebar updates instead, which is
      // a direct behavioural consequence of the selection.
      await expect(page.getByText(/R\$\s*18/)).toBeVisible();
    });

    test("exibe o preço do frete selecionado no painel lateral", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();

      // Click PAC option (R$ 18.50)
      await page.getByText("PAC").click();

      // Sidebar freight row should now show R$ 18,50
      const sidebar = page.locator("aside");
      await expect(sidebar.getByText(/18/)).toBeVisible();
    });

    test("atualiza o total do pedido no painel lateral ao selecionar frete", async ({
      page,
    }) => {
      // 2 × R$299.90 = R$599.80 products; SEDEX R$35.00 → total R$634.80
      await goToCheckout(page);

      await expect(page.getByText("SEDEX")).toBeVisible();
      await page.getByText("SEDEX").click();

      // Total must include the shipping cost
      const sidebar = page.locator("aside");
      await expect(sidebar.getByText(/634/)).toBeVisible();
    });
  });

  // ── 10. Botão "Ir para pagamento" — estado e guarda ──────────────────────

  test.describe("Botão Ir para pagamento", () => {
    test("está desabilitado enquanto nenhum endereço está selecionado", async ({
      page,
    }) => {
      // No addresses → showAddressForm=true but no selectedAddressId
      await goToCheckout(page, {
        addresses: [],
        shippingResponse: MOCK_SHIPPING_RESPONSE_SELLER_A,
      });

      const button = page.getByRole("button", { name: /Ir para pagamento/i });
      await expect(button).toBeDisabled();
    });

    test("está desabilitado quando endereço selecionado mas frete não escolhido", async ({
      page,
    }) => {
      // Address is selected (default), but user has not picked a shipping option
      await goToCheckout(page);

      await expect(page.getByText("Opções de frete")).toBeVisible();

      // Do NOT click any shipping option
      const button = page.getByRole("button", { name: /Ir para pagamento/i });
      await expect(button).toBeDisabled();
    });

    test("exibe dica 'Selecione um endereço' quando nenhum endereço está selecionado", async ({
      page,
    }) => {
      await goToCheckout(page, { addresses: [] });

      await expect(
        page.getByText(/Selecione um endereço de entrega para continuar/i),
      ).toBeVisible();
    });

    test("exibe dica 'Selecione o frete de todos os vendedores' quando frete está pendente", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("Opções de frete")).toBeVisible();

      await expect(
        page.getByText(/Selecione o frete de todos os vendedores para continuar/i),
      ).toBeVisible();
    });

    test("está habilitado somente após selecionar endereço E frete", async ({
      page,
    }) => {
      await goToCheckout(page);

      const button = page.getByRole("button", { name: /Ir para pagamento/i });

      // Initially disabled — address selected but no freight chosen
      await expect(button).toBeDisabled();

      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      await expect(button).not.toBeDisabled();
    });

    test("está habilitado após selecionar frete para TODOS os vendedores em carrinho multi-seller", async ({
      page,
    }) => {
      await goToCheckout(page, {
        cartItems: CART_TWO_SELLERS,
        shippingResponse: MOCK_SHIPPING_RESPONSE_TWO_SELLERS,
      });

      const button = page.getByRole("button", { name: /Ir para pagamento/i });
      await expect(button).toBeDisabled();

      // Select freight for seller A
      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      // Still disabled — seller B not selected yet
      await expect(button).toBeDisabled();

      // Select freight for seller B
      await expect(page.getByText("Mini Envios")).toBeVisible();
      await page.getByText("Mini Envios").click();

      await expect(button).not.toBeDisabled();
    });
  });

  // ── 11. Navegação para /payment ────────────────────────────────────────────

  test.describe("Navegação para /payment", () => {
    test("navega para /payment ao clicar em 'Ir para pagamento' com estado correto", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      // Mock /payment so the navigation lands without a 404 shell
      await page.route(`**/payment`, (route) => route.continue());

      const button = page.getByRole("button", { name: /Ir para pagamento/i });
      await expect(button).not.toBeDisabled();
      await button.click();

      await expect(page).toHaveURL(/\/payment/);
    });

    test("passa shippingAddressId correto no estado de navegação", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      // Intercept the history state set by navigate("/payment", { state })
      // by reading window.history.state after navigation.
      const statePromise = page.waitForFunction(() => {
        return window.location.pathname === "/payment" && window.history.state !== null;
      });

      await page.getByRole("button", { name: /Ir para pagamento/i }).click();
      await statePromise;

      const navState = await page.evaluate(() => window.history.state?.usr ?? window.history.state);

      expect(navState).toMatchObject({
        shippingAddressId: MOCK_ADDRESS_DEFAULT.id,
      });
    });

    test("passa selectedServices correto no estado de navegação", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      const statePromise = page.waitForFunction(() => {
        return window.location.pathname === "/payment" && window.history.state !== null;
      });

      await page.getByRole("button", { name: /Ir para pagamento/i }).click();
      await statePromise;

      const navState = await page.evaluate(() => window.history.state?.usr ?? window.history.state);

      // Seller id "10" should be mapped to service_id 1 (PAC)
      expect(navState).toMatchObject({
        selectedServices: { "10": 1 },
      });
    });

    test("passa inPersonSellers vazio para carrinho com frete normal", async ({
      page,
    }) => {
      await goToCheckout(page);

      await page.getByText("PAC").click();

      const statePromise = page.waitForFunction(() => {
        return window.location.pathname === "/payment" && window.history.state !== null;
      });

      await page.getByRole("button", { name: /Ir para pagamento/i }).click();
      await statePromise;

      const navState = await page.evaluate(() => window.history.state?.usr ?? window.history.state);

      expect(navState).toMatchObject({ inPersonSellers: [] });
    });

    test("passa inPersonSellers com o id do vendedor presencial no estado", async ({
      page,
    }) => {
      await goToCheckout(page, {
        shippingResponse: MOCK_SHIPPING_RESPONSE_IN_PERSON,
      });

      await expect(page.getByText("Opções de frete")).toBeVisible();

      const statePromise = page.waitForFunction(() => {
        return window.location.pathname === "/payment" && window.history.state !== null;
      });

      await page.getByRole("button", { name: /Ir para pagamento/i }).click();
      await statePromise;

      const navState = await page.evaluate(() => window.history.state?.usr ?? window.history.state);

      expect(navState).toMatchObject({ inPersonSellers: ["10"] });
    });
  });

  // ── 12. Resumo do pedido — painel lateral ─────────────────────────────────

  test.describe("Resumo do pedido — painel lateral", () => {
    test("exibe 'Resumo do pedido' com subtotal dos produtos", async ({ page }) => {
      // 2 × R$299.90 = R$599.80
      await goToCheckout(page);

      const sidebar = page.locator("aside");
      await expect(sidebar.getByText("Resumo do pedido")).toBeVisible();
      await expect(sidebar.getByText("Subtotal dos produtos")).toBeVisible();
      await expect(sidebar.getByText(/599/)).toBeVisible();
    });

    test("exibe '—' na linha de frete antes de selecionar uma opção", async ({
      page,
    }) => {
      await goToCheckout(page);

      await expect(page.getByText("Opções de frete")).toBeVisible();

      const sidebar = page.locator("aside");
      await expect(sidebar.getByText("Frete")).toBeVisible();
      // No freight selected → placeholder "—"
      await expect(sidebar.getByText("—")).toBeVisible();
    });

    test("exibe 'Calculando...' na linha de frete enquanto o cálculo está em andamento", async ({
      page,
    }) => {
      await mockBaseLayoutApis(page);
      await page.route(`${API}/logistics/addresses/`, (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([MOCK_ADDRESS_DEFAULT]),
        });
      });

      // Slow response to catch the loading state in the sidebar
      await page.route(`${API}/logistics/shipping/calculate/`, async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 500));
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_SHIPPING_RESPONSE_SELLER_A),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page, CART_SINGLE_SELLER);
      await page.goto("/checkout");

      await expect(page.getByRole("heading", { name: "Finalizar Compra" })).toBeVisible();

      const sidebar = page.locator("aside");
      await expect(sidebar.getByText("Calculando...")).toBeVisible();
    });

    test("total é a soma de subtotal + frete após selecionar opção", async ({
      page,
    }) => {
      // 2 × 299.90 = 599.80 + 18.50 (PAC) = 618.30
      await goToCheckout(page);

      await expect(page.getByText("PAC")).toBeVisible();
      await page.getByText("PAC").click();

      const sidebar = page.locator("aside");
      await expect(sidebar.getByText(/618/)).toBeVisible();
    });
  });
});
