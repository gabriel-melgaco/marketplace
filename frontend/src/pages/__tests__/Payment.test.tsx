import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import React from 'react';

// ── Mocks ────────────────────────────────────────────────────────────────────

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@stripe/stripe-js', () => ({
  loadStripe: vi.fn(() => Promise.resolve({})),
}));

vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="stripe-elements">{children}</div>,
  CardElement: () => <div data-testid="card-element" />,
  useStripe: vi.fn(() => ({
    confirmCardPayment: vi.fn().mockResolvedValue({ error: null }),
  })),
  useElements: vi.fn(() => ({
    getElement: vi.fn(() => ({})),
  })),
}));

const { mockGetPaymentStatus } = vi.hoisted(() => ({
  mockGetPaymentStatus: vi.fn(),
}));

vi.mock('@/services/paymentService', () => ({
  paymentService: { getPaymentStatus: mockGetPaymentStatus },
}));

const { mockApiPost } = vi.hoisted(() => ({ mockApiPost: vi.fn() }));
vi.mock('@/api/axios', () => ({
  default: { post: mockApiPost, get: vi.fn() },
}));

const { mockUseCart } = vi.hoisted(() => ({ mockUseCart: vi.fn() }));
vi.mock('@/contexts/CartContext', () => ({ useCart: mockUseCart }));

// ── Stripe env guard ─────────────────────────────────────────────────────────

vi.stubEnv('VITE_STRIPE_PUBLIC_KEY', 'pk_test_dummy');

// ── Import after all mocks are set ───────────────────────────────────────────

import { Payment, CheckoutNavigationState } from '@/pages/Payment/index';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const CHECKOUT_STATE: CheckoutNavigationState = {
  shippingAddressId: 1,
  selectedServices: { '5': 100 },
  inPersonSellers: [],
};

const CART_ITEMS = [
  { listing: { id: 10, seller: 5, title: 'Product A', price: '99.90' }, quantity: 1 },
];

function renderPayment(locationState: CheckoutNavigationState | null = CHECKOUT_STATE) {
  mockUseCart.mockReturnValue({ items: CART_ITEMS });
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/payment', state: locationState }]}>
      <Routes>
        <Route path="/payment" element={<Payment />} />
        <Route path="/checkout" element={<div>Checkout</div>} />
        <Route path="/payment/success" element={<div>Success</div>} />
        <Route path="/payment/failed" element={<div>Failed</div>} />
        <Route path="/payment/processing" element={<div>Processing</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Payment page', () => {
  describe('guard — no checkout state', () => {
    it('redirects to /checkout when locationState is null', async () => {
      renderPayment(null);
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/checkout', { replace: true });
      });
    });
  });

  describe('order creation', () => {
    it('shows "Criando seu pedido..." loading banner on mount', () => {
      mockApiPost.mockReturnValue(new Promise(() => {}));
      renderPayment();
      expect(screen.getByLabelText('Criando pedido')).toBeInTheDocument();
    });

    it('shows order created confirmation after order succeeds', async () => {
      mockApiPost.mockResolvedValueOnce({ data: { id: 42 } });
      renderPayment();
      await waitFor(() => {
        expect(screen.getByText('Pedido criado. Escolha como pagar.')).toBeInTheDocument();
      });
    });

    it('shows error alert when order creation fails', async () => {
      mockApiPost.mockRejectedValueOnce({
        response: { data: { detail: 'Insufficient stock' } },
      });
      renderPayment();
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });
  });

  describe('payment method selection', () => {
    async function renderAndWaitForOrder() {
      mockApiPost.mockResolvedValueOnce({ data: { id: 42 } });
      renderPayment();
      await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'));
    }

    it('renders both payment method options', async () => {
      await renderAndWaitForOrder();
      expect(screen.getByText('Cartão de Crédito')).toBeInTheDocument();
      expect(screen.getByText('Cartão de Débito')).toBeInTheDocument();
    });

    it('credit_card is selected by default', async () => {
      await renderAndWaitForOrder();
      const creditCard = screen.getByRole('radio', { name: /Cartão de Crédito/i });
      expect(creditCard).toHaveAttribute('aria-checked', 'true');
    });

    it('switches to debit_card on click', async () => {
      await renderAndWaitForOrder();
      const debitCard = screen.getByRole('radio', { name: /Cartão de Débito/i });
      await userEvent.click(debitCard);
      expect(debitCard).toHaveAttribute('aria-checked', 'true');
    });

    it('"Continuar" button is disabled while order is loading', () => {
      mockApiPost.mockReturnValue(new Promise(() => {}));
      renderPayment();
      expect(screen.getByRole('button', { name: /Continuar para pagamento/i })).toBeDisabled();
    });

    it('"Continuar" button is enabled after order is created', async () => {
      await renderAndWaitForOrder();
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Continuar para pagamento/i })).not.toBeDisabled();
      });
    });
  });

  describe('payment intent creation', () => {
    async function renderAndGetContinueButton() {
      mockApiPost.mockResolvedValueOnce({ data: { id: 42 } });
      renderPayment();
      await waitFor(() => screen.getByRole('button', { name: /Continuar para pagamento/i }));
      return screen.getByRole('button', { name: /Continuar para pagamento/i });
    }

    it('shows Stripe card form after payment intent is created', async () => {
      const continueBtn = await renderAndGetContinueButton();
      mockApiPost.mockResolvedValueOnce({
        data: { id: 1, client_secret: 'cs_test', stripe_payment_intent_id: 'pi_123', status: 'requires_payment_method' },
      });
      await userEvent.click(continueBtn);
      await waitFor(() => {
        expect(screen.getByTestId('stripe-elements')).toBeInTheDocument();
      });
    });

    it('shows intent error when payment intent creation fails', async () => {
      const continueBtn = await renderAndGetContinueButton();
      mockApiPost.mockRejectedValueOnce({
        response: { data: { detail: 'Order already paid' } },
      });
      await userEvent.click(continueBtn);
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });

    it('prevents double-click: only one intent request made', async () => {
      const continueBtn = await renderAndGetContinueButton();
      // Intent request never resolves — simulates slow network
      mockApiPost.mockReturnValue(new Promise(() => {}));
      await userEvent.click(continueBtn);
      await userEvent.click(continueBtn);
      // 1 call for order creation + 1 for intent (second click is no-op)
      expect(mockApiPost).toHaveBeenCalledTimes(2);
    });
  });

  describe('payment polling', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    async function renderToPollingState() {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      mockApiPost
        .mockResolvedValueOnce({ data: { id: 42 } }) // order
        .mockResolvedValueOnce({
          data: {
            id: 1,
            client_secret: 'cs_test',
            stripe_payment_intent_id: 'pi_123',
            status: 'requires_payment_method',
          },
        }); // intent
      mockUseCart.mockReturnValue({ items: CART_ITEMS });

      render(
        <MemoryRouter initialEntries={[{ pathname: '/payment', state: CHECKOUT_STATE }]}>
          <Routes>
            <Route path="/payment" element={<Payment />} />
          </Routes>
        </MemoryRouter>
      );

      // Wait for order to be created
      await vi.runAllTimersAsync();
      await waitFor(() => screen.getByRole('button', { name: /Continuar para pagamento/i }));

      // Click continue to trigger intent
      await userEvent.click(screen.getByRole('button', { name: /Continuar para pagamento/i }));
      await vi.runAllTimersAsync();
      await waitFor(() => screen.getByTestId('stripe-elements'));

      // Click confirm to trigger polling
      await userEvent.click(screen.getByRole('button', { name: /Confirmar Pagamento/i }));
      await vi.runAllTimersAsync();
    }

    it('shows processing spinner when polling starts', async () => {
      await renderToPollingState();
      expect(screen.getByLabelText('Processando pagamento')).toBeInTheDocument();
    });

    it('navigates to /payment/success when status becomes succeeded', async () => {
      mockGetPaymentStatus.mockResolvedValue({ status: 'succeeded' });
      await renderToPollingState();

      await act(async () => {
        vi.advanceTimersByTime(2000);
        await Promise.resolve();
      });

      expect(mockNavigate).toHaveBeenCalledWith('/payment/success', { state: { orderId: 42 } });
    });

    it('navigates to /payment/failed when status becomes failed', async () => {
      mockGetPaymentStatus.mockResolvedValue({ status: 'failed' });
      await renderToPollingState();

      await act(async () => {
        vi.advanceTimersByTime(2000);
        await Promise.resolve();
      });

      expect(mockNavigate).toHaveBeenCalledWith('/payment/failed');
    });

    it('navigates to /payment/processing after exhausting all 10 poll attempts', async () => {
      mockGetPaymentStatus.mockResolvedValue({ status: 'processing' });
      await renderToPollingState();

      await act(async () => {
        for (let i = 0; i < 10; i++) {
          vi.advanceTimersByTime(2000);
          await Promise.resolve();
        }
      });

      expect(mockNavigate).toHaveBeenCalledWith('/payment/processing', { state: { orderId: 42 } });
    });
  });

  describe('back navigation', () => {
    it('navigates to /checkout when back button is clicked', async () => {
      mockApiPost.mockResolvedValueOnce({ data: { id: 42 } });
      renderPayment();
      await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'));
      await userEvent.click(screen.getByRole('button', { name: /Voltar ao checkout/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/checkout');
    });
  });
});
