import { test, expect } from "@playwright/test";
import { injectAuth } from "./helpers/auth";

// ─── API Base ──────────────────────────────────────────────────────────────────
// Matches the VITE_API_URL default consumed by the app's axios instance.
const API = "http://localhost:8000";

// ─── Storage Keys ─────────────────────────────────────────────────────────────
const CART_STORAGE_KEY = "cart_items";

// ─── Mock Fixtures ─────────────────────────────────────────────────────────────

const MOCK_LISTING = {
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

const CART_ITEMS = [{ listing: MOCK_LISTING, quantity: 1 }];

/**
 * The navigation state that the checkout page passes to /payment when
 * the user proceeds to payment. Must match CheckoutNavigationState shape.
 */
const CHECKOUT_NAV_STATE = {
  shippingAddressId: 1,
  selectedServices: { "10": 1 },
  inPersonSellers: [],
};

/** Successful order creation response. */
const MOCK_ORDER_RESPONSE = { id: "order-abc-123" };

/** Successful payment intent response. */
const MOCK_INTENT_RESPONSE = {
  id: 42,
  client_secret: "pi_test_secret_xyz",
  stripe_payment_intent_id: "pi_test_xyz",
  status: "requires_payment_method",
};

/** Payment status response indicating success. */
const MOCK_STATUS_SUCCEEDED = {
  id: 42,
  order: "order-abc-123",
  amount: "299.90",
  status: "succeeded",
  payment_method: "credit_card",
  stripe_payment_intent_id: "pi_test_xyz",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

/** Payment status response indicating failure. */
const MOCK_STATUS_FAILED = { ...MOCK_STATUS_SUCCEEDED, status: "failed" };

/** Payment status response still pending (used to exhaust poll attempts). */
const MOCK_STATUS_PENDING = { ...MOCK_STATUS_SUCCEEDED, status: "pending" };

// ─── Stripe Mock ──────────────────────────────────────────────────────────────

/**
 * Installs a window.Stripe stub before any page scripts run.
 *
 * The stub replaces the real Stripe.js so that:
 *  - loadStripe() from @stripe/stripe-js resolves immediately to the stub.
 *  - The <Elements> provider is satisfied.
 *  - stripe.confirmCardPayment() can be controlled per-test via
 *    window.__mockConfirmResult set in the test body.
 *
 * This must be registered with page.addInitScript() so it executes before the
 * app bundle, which calls loadStripe() at module evaluation time.
 */
async function installStripeMock(page: import("@playwright/test").Page) {
  // Also block the real Stripe.js CDN request so nothing external loads.
  await page.route("https://js.stripe.com/**", (route) => route.fulfill({ status: 200, body: "" }));

  await page.addInitScript(() => {
    // A minimal CardElement that renders a placeholder div the app can mount.
    const fakeCardElement = {
      mount: () => {},
      unmount: () => {},
      destroy: () => {},
      on: () => fakeCardElement,
      off: () => fakeCardElement,
      update: () => {},
    };

    const fakeElements = {
      getElement: () => fakeCardElement,
      create: () => fakeCardElement,
    };

    const fakeStripe = {
      elements: () => fakeElements,
      confirmCardPayment: async (_secret: string) => {
        // Tests set window.__mockConfirmResult to control the outcome.
        const result = (window as unknown as Record<string, unknown>).__mockConfirmResult;
        if (result !== undefined) return result;
        // Default: success with no error.
        return { error: undefined, paymentIntent: { status: "succeeded" } };
      },
      createToken: async () => ({ token: { id: "tok_test" } }),
      createPaymentMethod: async () => ({ paymentMethod: { id: "pm_test" } }),
    };

    // Override the module-level loadStripe call.  @stripe/stripe-js checks
    // window.Stripe and returns it directly when available.
    (window as unknown as Record<string, unknown>).Stripe = () => fakeStripe;

    // Also expose the fake stripe instance so addInitScript injections can
    // resolve the stripePromise used by <Elements>.
    (window as unknown as Record<string, unknown>).__fakeStripe = fakeStripe;
  });
}

// ─── Shared Setup Helpers ─────────────────────────────────────────────────────

/**
 * Mocks layout-level API calls that fire on every page load (header categories,
 * home listings). Keeps them quiet so they do not interfere with test assertions.
 */
async function mockBaseLayoutApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/products/listings/`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
    }),
  );

  await page.route(`${API}/products/categories/`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: 0, next: null, results: [] }),
    }),
  );
}

/**
 * Seeds the cart in localStorage.
 * Must be called after page.goto() so the origin is established.
 */
async function seedCart(page: import("@playwright/test").Page) {
  await page.evaluate(
    ({ key, data }) => {
      localStorage.setItem(key, JSON.stringify(data));
    },
    { key: CART_STORAGE_KEY, data: CART_ITEMS },
  );
}

/**
 * Navigates to /payment with the required location.state by:
 *  1. Going to "/" to establish the origin and inject auth + cart.
 *  2. Using history.pushState to inject the checkout navigation state.
 *  3. Navigating to /payment — React Router will pick up the injected state.
 *
 * Because React Router reads history.state, we push the state and then
 * navigate so the component's useLocation().state is populated.
 */
async function goToPayment(
  page: import("@playwright/test").Page,
  options: {
    orderResponse?: object | null;
    orderStatus?: number;
    skipOrderMock?: boolean;
  } = {},
) {
  const {
    orderResponse = MOCK_ORDER_RESPONSE,
    orderStatus = 200,
    skipOrderMock = false,
  } = options;

  await mockBaseLayoutApis(page);

  if (!skipOrderMock) {
    await page.route(`${API}/orders/create/`, (route) => {
      if (orderResponse === null) {
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Erro interno no servidor." }),
        });
      } else {
        route.fulfill({
          status: orderStatus,
          contentType: "application/json",
          body: JSON.stringify(orderResponse),
        });
      }
    });
  }

  // Navigate to origin first to establish localStorage scope.
  await page.goto("/");
  await injectAuth(page);
  await seedCart(page);

  // Inject location.state that the Payment component expects.
  // We push a history entry for "/payment" with the state, then navigate there.
  await page.evaluate((state) => {
    history.pushState(state, "", "/payment");
  }, CHECKOUT_NAV_STATE);

  // Full navigation so React Router re-initialises and reads the state.
  await page.goto("/payment");

  // Wait for the page heading to confirm we are on the payment page.
  await expect(page.getByRole("heading", { name: "Pagamento" })).toBeVisible();
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

test.describe("Payment", () => {
  // ── 1. Route guard — no location.state ─────────────────────────────────────

  test.describe("Proteção de rota", () => {
    test("redireciona para /checkout quando não há location.state", async ({ page }) => {
      await installStripeMock(page);
      await mockBaseLayoutApis(page);

      // Navigate directly to /payment without going through checkout — no state.
      await page.goto("/");
      await injectAuth(page);
      await seedCart(page);

      // Direct navigation does not inject location.state, so the component
      // should immediately call navigate("/checkout", { replace: true }).
      await page.goto("/payment");

      await expect(page).toHaveURL(/\/checkout/);
    });
  });

  // ── 2. Order creation banner ────────────────────────────────────────────────

  test.describe("Criação de pedido", () => {
    test("exibe banner 'Criando seu pedido...' enquanto a chamada de criação está pendente", async ({
      page,
    }) => {
      await installStripeMock(page);
      await mockBaseLayoutApis(page);

      // Use a promise-based route that resolves only when the test triggers it,
      // so we can assert while the request is still in flight.
      let resolveOrder!: () => void;
      const orderHeld = new Promise<void>((res) => {
        resolveOrder = res;
      });

      await page.route(`${API}/orders/create/`, async (route) => {
        await orderHeld; // Hold the response until we release it.
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_ORDER_RESPONSE),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page);

      await page.evaluate((state) => {
        history.pushState(state, "", "/payment");
      }, CHECKOUT_NAV_STATE);

      await page.goto("/payment");
      await expect(page.getByRole("heading", { name: "Pagamento" })).toBeVisible();

      // The loading banner should be visible while the request is held.
      await expect(page.getByText("Criando seu pedido...")).toBeVisible();

      // Release the order response.
      resolveOrder();
    });

    test("exibe banner 'Pedido criado com sucesso.' após criação bem-sucedida", async ({
      page,
    }) => {
      await installStripeMock(page);

      await goToPayment(page);

      // After the mock resolves the order, the success banner appears.
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
    });

    test("exibe erro e botão de voltar quando a API de criação de pedido falha", async ({
      page,
    }) => {
      await installStripeMock(page);

      await goToPayment(page, { orderResponse: null });

      // The error message from the mock 500 response.
      await expect(page.getByText(/Erro interno no servidor\.|Erro ao criar o pedido\./)).toBeVisible();

      // The back link to checkout should be present.
      await expect(page.getByRole("button", { name: /Voltar ao checkout/i })).toBeVisible();
    });

    test("clicar em 'Voltar ao checkout' no estado de erro navega para /checkout", async ({
      page,
    }) => {
      await installStripeMock(page);

      await goToPayment(page, { orderResponse: null });

      await expect(page.getByRole("button", { name: /Voltar ao checkout/i })).toBeVisible();
      await page.getByRole("button", { name: /Voltar ao checkout/i }).click();

      await expect(page).toHaveURL(/\/checkout/);
    });
  });

  // ── 3. Seleção de método de pagamento ──────────────────────────────────────

  test.describe("Método de pagamento", () => {
    test("'Cartão de Crédito' está selecionado por padrão", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      // The credit card option has aria-checked="true" by default.
      const creditCardOption = page.getByRole("radio", { name: /Cartão de Crédito/i });
      await expect(creditCardOption).toHaveAttribute("aria-checked", "true");
    });

    test("pode selecionar 'Cartão de Débito'", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      const debitCardOption = page.getByRole("radio", { name: /Cartão de Débito/i });
      await debitCardOption.click();

      await expect(debitCardOption).toHaveAttribute("aria-checked", "true");

      // Credit card should no longer be selected.
      const creditCardOption = page.getByRole("radio", { name: /Cartão de Crédito/i });
      await expect(creditCardOption).toHaveAttribute("aria-checked", "false");
    });

    test("pode selecionar método via teclado (Enter)", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      const debitCardOption = page.getByRole("radio", { name: /Cartão de Débito/i });
      await debitCardOption.focus();
      await page.keyboard.press("Enter");

      await expect(debitCardOption).toHaveAttribute("aria-checked", "true");
    });

    test("pode selecionar método via teclado (Space)", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      const debitCardOption = page.getByRole("radio", { name: /Cartão de Débito/i });
      await debitCardOption.focus();
      await page.keyboard.press("Space");

      await expect(debitCardOption).toHaveAttribute("aria-checked", "true");
    });
  });

  // ── 4. Botão "Continuar para pagamento" ───────────────────────────────────

  test.describe("Botão Continuar para pagamento", () => {
    test("está desabilitado enquanto o pedido está sendo criado", async ({ page }) => {
      await installStripeMock(page);
      await mockBaseLayoutApis(page);

      // Hold the order response so we can inspect the button while loading.
      let resolveOrder!: () => void;
      const orderHeld = new Promise<void>((res) => {
        resolveOrder = res;
      });

      await page.route(`${API}/orders/create/`, async (route) => {
        await orderHeld;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_ORDER_RESPONSE),
        });
      });

      await page.goto("/");
      await injectAuth(page);
      await seedCart(page);
      await page.evaluate((state) => {
        history.pushState(state, "", "/payment");
      }, CHECKOUT_NAV_STATE);
      await page.goto("/payment");

      await expect(page.getByRole("heading", { name: "Pagamento" })).toBeVisible();

      const continueButton = page.getByRole("button", { name: /Continuar para pagamento/i });
      await expect(continueButton).toBeDisabled();

      resolveOrder();
    });

    test("está habilitado após o pedido ser criado com sucesso", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      // Wait for the success banner so the order is confirmed ready.
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();

      const continueButton = page.getByRole("button", { name: /Continuar para pagamento/i });
      await expect(continueButton).toBeEnabled();
    });
  });

  // ── 5. Criação de intent de pagamento e formulário Stripe ─────────────────

  test.describe("Intent de pagamento e formulário de cartão", () => {
    test("clicar em 'Continuar para pagamento' dispara POST /payments/create-intent/", async ({
      page,
    }) => {
      await installStripeMock(page);

      let intentCalled = false;

      await page.route(`${API}/payments/create-intent/`, (route) => {
        intentCalled = true;
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        });
      });

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();

      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();

      // Allow the async call to complete.
      await page.waitForTimeout(300);
      expect(intentCalled).toBe(true);
    });

    test("seção 'Dados do cartão' aparece após criação bem-sucedida do intent", async ({
      page,
    }) => {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();

      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();

      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).toBeVisible();
    });

    test("seletor de método de pagamento desaparece após exibir formulário de cartão", async ({
      page,
    }) => {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();

      // The payment method radiogroup must be gone once the card form is shown.
      await expect(
        page.getByRole("radiogroup", { name: /Método de pagamento/i }),
      ).not.toBeVisible();
    });

    test("exibe erro inline quando create-intent falha", async ({ page }) => {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Falha ao criar intent." }),
        }),
      );

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();

      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();

      await expect(
        page.getByText(/Falha ao criar intent\.|Erro ao inicializar pagamento\./),
      ).toBeVisible();

      // The card form section must NOT appear on intent failure.
      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).not.toBeVisible();
    });
  });

  // ── 6. Polling de status de pagamento ─────────────────────────────────────

  test.describe("Polling de status", () => {
    /**
     * Helper: brings the page to the state just after confirmCardPayment succeeds
     * and polling has begun, with the status endpoint mocked to return `mockStatus`.
     */
    async function reachPollingState(
      page: import("@playwright/test").Page,
      statusBody: object,
    ) {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      // Mock confirmCardPayment to succeed (no error) so polling begins.
      await page.addInitScript(() => {
        (window as unknown as Record<string, unknown>).__mockConfirmResult = {
          error: undefined,
          paymentIntent: { status: "succeeded" },
        };
      });

      // Mock the polling endpoint — match by glob because the intent ID is in the path.
      await page.route(`${API}/payments/status/**`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(statusBody),
        }),
      );

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();
      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).toBeVisible();

      // Trigger payment confirmation via the "Confirmar Pagamento" button.
      await page.getByRole("button", { name: /Confirmar Pagamento/i }).click();
    }

    test("navega para /payment/success após status 'succeeded'", async ({ page }) => {
      await reachPollingState(page, MOCK_STATUS_SUCCEEDED);

      // Polling interval is 2000 ms; wait enough for at least one tick.
      await expect(page).toHaveURL(/\/payment\/success/, { timeout: 8000 });
    });

    test("navega para /payment/failed após status 'failed'", async ({ page }) => {
      await reachPollingState(page, MOCK_STATUS_FAILED);

      await expect(page).toHaveURL(/\/payment\/failed/, { timeout: 8000 });
    });

    test("navega para /payment/processing após esgotar 10 tentativas sem sucesso", async ({
      page,
    }) => {
      // Override to always return a pending status so all 10 attempts exhaust.
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      await page.addInitScript(() => {
        (window as unknown as Record<string, unknown>).__mockConfirmResult = {
          error: undefined,
          paymentIntent: { status: "requires_capture" },
        };
      });

      await page.route(`${API}/payments/status/**`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_STATUS_PENDING),
        }),
      );

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();
      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).toBeVisible();
      await page.getByRole("button", { name: /Confirmar Pagamento/i }).click();

      // 10 attempts × 2000 ms = 20 s; give generous timeout.
      await expect(page).toHaveURL(/\/payment\/processing/, { timeout: 30000 });
    });

    test("exibe estado 'Processando pagamento...' imediatamente após confirmação", async ({
      page,
    }) => {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      await page.addInitScript(() => {
        (window as unknown as Record<string, unknown>).__mockConfirmResult = {
          error: undefined,
        };
      });

      // Hold the status response indefinitely to keep the polling state visible.
      await page.route(`${API}/payments/status/**`, (_route) => {
        // Never resolve — keeps the component in polling mode.
      });

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();
      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).toBeVisible();
      await page.getByRole("button", { name: /Confirmar Pagamento/i }).click();

      await expect(page.getByText("Processando pagamento...")).toBeVisible();
    });

    test("exibe erro do Stripe inline quando confirmCardPayment retorna um erro", async ({
      page,
    }) => {
      await installStripeMock(page);

      await page.route(`${API}/payments/create-intent/`, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_INTENT_RESPONSE),
        }),
      );

      // Make the Stripe mock return an error.
      await page.addInitScript(() => {
        (window as unknown as Record<string, unknown>).__mockConfirmResult = {
          error: { message: "Cartão recusado." },
        };
      });

      await goToPayment(page);
      await expect(page.getByText("Pedido criado com sucesso.")).toBeVisible();
      await page.getByRole("button", { name: /Continuar para pagamento/i }).click();
      await expect(page.getByRole("heading", { name: /Dados do cartão/i })).toBeVisible();
      await page.getByRole("button", { name: /Confirmar Pagamento/i }).click();

      await expect(page.getByText("Cartão recusado.")).toBeVisible();

      // Must stay on /payment — no navigation.
      await expect(page).toHaveURL(/\/payment/);
      await expect(page).not.toHaveURL(/\/payment\/(success|failed|processing)/);
    });
  });

  // ── 7. Página PaymentSuccess ────────────────────────────────────────────────

  test.describe("PaymentSuccess (/payment/success)", () => {
    /**
     * Navigates directly to /payment/success with an orderId in location.state.
     * This simulates the navigation performed by the polling effect.
     */
    async function goToPaymentSuccess(
      page: import("@playwright/test").Page,
      orderId = "order-abc-123",
    ) {
      await mockBaseLayoutApis(page);
      await page.goto("/");
      await injectAuth(page);

      // Seed the cart so we can verify it gets cleared.
      await seedCart(page);
      const cartBefore = await page.evaluate((key) => localStorage.getItem(key), CART_STORAGE_KEY);
      expect(cartBefore).not.toBeNull();

      // Inject location.state for the success page.
      await page.evaluate((state) => {
        history.pushState(state, "", "/payment/success");
      }, { orderId });

      await page.goto("/payment/success");
    }

    test("exibe 'Pagamento confirmado!' na página de sucesso", async ({ page }) => {
      await goToPaymentSuccess(page);

      await expect(page.getByRole("heading", { name: "Pagamento confirmado!" })).toBeVisible();
    });

    test("limpa o carrinho (localStorage) ao renderizar a página de sucesso", async ({ page }) => {
      await goToPaymentSuccess(page);

      await expect(page.getByRole("heading", { name: "Pagamento confirmado!" })).toBeVisible();

      // The useEffect in PaymentSuccess calls clearCart(), which removes the key.
      const cartAfter = await page.evaluate((key) => localStorage.getItem(key), CART_STORAGE_KEY);
      expect(cartAfter).toBeNull();
    });

    test("exibe botão 'Ver meu pedido' com link para /orders/:orderId quando orderId está presente", async ({
      page,
    }) => {
      await goToPaymentSuccess(page, "order-abc-123");

      await expect(page.getByRole("button", { name: /Ver meu pedido/i })).toBeVisible();
    });

    test("clicar em 'Ver meu pedido' navega para /orders/:orderId", async ({ page }) => {
      await goToPaymentSuccess(page, "order-abc-123");

      await page.getByRole("button", { name: /Ver meu pedido/i }).click();

      await expect(page).toHaveURL(/\/orders\/order-abc-123/);
    });

    test("exibe botão 'Continuar comprando' que navega para /", async ({ page }) => {
      await goToPaymentSuccess(page);

      const btn = page.getByRole("button", { name: /Continuar comprando/i });
      await expect(btn).toBeVisible();
      await btn.click();

      await expect(page).toHaveURL(/^\//);
      await expect(page).not.toHaveURL(/\/payment/);
    });

    test("não exibe botão 'Ver meu pedido' quando não há orderId no state", async ({ page }) => {
      await mockBaseLayoutApis(page);
      await page.goto("/");
      await injectAuth(page);

      // Navigate without state so orderId is undefined.
      await page.goto("/payment/success");

      await expect(page.getByRole("heading", { name: "Pagamento confirmado!" })).toBeVisible();
      await expect(page.getByRole("button", { name: /Ver meu pedido/i })).not.toBeVisible();
    });
  });

  // ── 8. Página PaymentProcessing ─────────────────────────────────────────────

  test.describe("PaymentProcessing (/payment/processing)", () => {
    async function goToPaymentProcessing(
      page: import("@playwright/test").Page,
      orderId?: string,
    ) {
      await mockBaseLayoutApis(page);
      await page.goto("/");
      await injectAuth(page);

      if (orderId) {
        await page.evaluate((state) => {
          history.pushState(state, "", "/payment/processing");
        }, { orderId });
      }

      await page.goto("/payment/processing");
    }

    test("exibe 'Pagamento em processamento' na página de processamento", async ({ page }) => {
      await goToPaymentProcessing(page, "order-abc-123");

      await expect(
        page.getByRole("heading", { name: "Pagamento em processamento" }),
      ).toBeVisible();
    });

    test("exibe botão 'Ver status do pedido' quando orderId está presente no state", async ({
      page,
    }) => {
      await goToPaymentProcessing(page, "order-abc-123");

      await expect(page.getByRole("button", { name: /Ver status do pedido/i })).toBeVisible();
    });

    test("clicar em 'Ver status do pedido' navega para /orders/:orderId", async ({ page }) => {
      await goToPaymentProcessing(page, "order-abc-123");

      await page.getByRole("button", { name: /Ver status do pedido/i }).click();

      await expect(page).toHaveURL(/\/orders\/order-abc-123/);
    });

    test("não exibe botão 'Ver status do pedido' quando não há orderId", async ({ page }) => {
      await goToPaymentProcessing(page);

      await expect(
        page.getByRole("heading", { name: "Pagamento em processamento" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: /Ver status do pedido/i }),
      ).not.toBeVisible();
    });
  });

  // ── 9. Página PaymentFailed ──────────────────────────────────────────────────

  test.describe("PaymentFailed (/payment/failed)", () => {
    async function goToPaymentFailed(page: import("@playwright/test").Page) {
      await mockBaseLayoutApis(page);
      await page.goto("/");
      await injectAuth(page);
      await page.goto("/payment/failed");
    }

    test("exibe 'Pagamento não realizado' na página de falha", async ({ page }) => {
      await goToPaymentFailed(page);

      await expect(page.getByRole("heading", { name: "Pagamento não realizado" })).toBeVisible();
    });

    test("exibe botão 'Tentar novamente' na página de falha", async ({ page }) => {
      await goToPaymentFailed(page);

      await expect(page.getByRole("button", { name: /Tentar novamente/i })).toBeVisible();
    });

    test("clicar em 'Tentar novamente' navega para /payment", async ({ page }) => {
      await goToPaymentFailed(page);

      await page.getByRole("button", { name: /Tentar novamente/i }).click();

      // Should land on /payment — the route guard will then redirect to /checkout
      // if there is no state, but the navigation target is /payment.
      await expect(page).toHaveURL(/\/payment/);
    });

    test("exibe botão 'Voltar às compras' que navega para /", async ({ page }) => {
      await goToPaymentFailed(page);

      const btn = page.getByRole("button", { name: /Voltar às compras/i });
      await expect(btn).toBeVisible();
      await btn.click();

      await expect(page).toHaveURL(/^\//);
      await expect(page).not.toHaveURL(/\/payment/);
    });
  });

  // ── 10. Navegação geral ──────────────────────────────────────────────────────

  test.describe("Navegação geral", () => {
    test("botão 'Voltar ao checkout' no topo da página navega para /checkout", async ({
      page,
    }) => {
      await installStripeMock(page);

      await goToPayment(page);

      await page.getByRole("button", { name: /Voltar ao checkout/i }).first().click();

      await expect(page).toHaveURL(/\/checkout/);
    });

    test("trust badge 'Pagamento seguro com Stripe' está visível", async ({ page }) => {
      await installStripeMock(page);

      await goToPayment(page);

      await expect(page.getByText(/Pagamento seguro com Stripe/i)).toBeVisible();
    });
  });
});
