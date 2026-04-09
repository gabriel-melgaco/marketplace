import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import React from 'react'

// ── Mocks de módulos — ANTES dos imports de componentes ──────────────────────

vi.mock('@stripe/stripe-js', () => ({
  loadStripe: vi.fn(() => Promise.resolve(null)),
}))

vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PaymentElement: () => <div data-testid="payment-element" />,
  useStripe: vi.fn(),
  useElements: vi.fn(),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}))

vi.mock('@/api/axios', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    delete: vi.fn(),
  },
}))

vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      isAxiosError: (err: unknown) =>
        !!(err && typeof err === 'object' && 'response' in err),
      isCancel: vi.fn(() => false),
    },
    isAxiosError: (err: unknown) =>
      !!(err && typeof err === 'object' && 'response' in err),
    isCancel: vi.fn(() => false),
  }
})

const mockSwalFire = vi.fn(() => Promise.resolve({ isConfirmed: true }))
vi.mock('sweetalert2', () => ({
  default: { fire: (...args: unknown[]) => mockSwalFire(...args) },
}))

// ── Imports de componentes APÓS os mocks ─────────────────────────────────────

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Payment } from '../index'
import { mockCheckoutState, mockOrderCreateResponse, mockPaymentIntentResponse } from './fixtures'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderPayment(locationState: unknown = mockCheckoutState) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/payment', state: locationState }]}>
      <Payment />
    </MemoryRouter>,
  )
}

// ── Testes ────────────────────────────────────────────────────────────────────

describe('Navegação direta para /payment sem checkoutState', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('redireciona para /checkout com replace=true quando location.state é null', async () => {
    renderPayment(null)
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/checkout', { replace: true })
    })
  })

  it('não chama POST /orders/create/ quando checkoutState é null', async () => {
    renderPayment(null)
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled())
    expect(mockPost).not.toHaveBeenCalledWith(
      '/orders/create/',
      expect.anything(),
      expect.anything(),
    )
  })
})

describe('Guard anti-duplo-submit em StripeCardForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('segundo clique em "Confirmar Pagamento" não chama stripe.confirmPayment() novamente', async () => {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    // confirmPayment nunca resolve para simular processamento em andamento
    const confirmPaymentMock = vi.fn().mockReturnValue(new Promise(() => {}))
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: confirmPaymentMock,
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })

    renderPayment()
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))

    const confirmBtn = screen.getByRole('button', { name: /confirmar pagamento/i })
    fireEvent.click(confirmBtn)
    fireEvent.click(confirmBtn)
    fireEvent.click(confirmBtn)

    // Apenas uma chamada deve ter ocorrido
    expect(confirmPaymentMock).toHaveBeenCalledTimes(1)
  })
})

describe('400 "cotação expirada" em /payment → redireciona /checkout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('redireciona para /checkout com state.error quando POST /orders/create/ retorna 400 com "cotação"', async () => {
    mockPost.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'cotação inválida' } },
    })
    renderPayment()
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        '/checkout',
        expect.objectContaining({ state: expect.objectContaining({ error: expect.any(String) }) }),
      )
    })
  })

  it('redireciona para /checkout quando mensagem contém "expirada"', async () => {
    mockPost.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'cotação expirada' } },
    })
    renderPayment()
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        '/checkout',
        expect.objectContaining({ state: expect.objectContaining({ error: expect.any(String) }) }),
      )
    })
  })

  it('não exibe orderError inline — apenas redireciona', async () => {
    mockPost.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'cotação expirada' } },
    })
    renderPayment()
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled())
    // Não deve exibir o botão "Voltar ao checkout" de erro inline
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('422 insufficient_me_balance em /payment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('exibe Swal.fire com icon="error" e não navega para rota alguma', async () => {
    mockPost.mockRejectedValueOnce({
      response: { status: 422, data: { error: 'insufficient_me_balance' } },
    })
    renderPayment()
    await waitFor(() => {
      expect(mockSwalFire).toHaveBeenCalledWith(
        expect.objectContaining({ icon: 'error' }),
      )
    })
    const paymentNavCalls = mockNavigate.mock.calls.filter(
      ([route]) => route === '/payment/success' || route === '/payment/failed' || route === '/payment/processing',
    )
    expect(paymentNavCalls).toHaveLength(0)
  })

  it('mantém o usuário na página de pagamento após fechar o Swal', async () => {
    mockSwalFire.mockResolvedValueOnce({ isConfirmed: true })
    mockPost.mockRejectedValueOnce({
      response: { status: 422, data: { error: 'insufficient_me_balance' } },
    })
    renderPayment()
    await waitFor(() => expect(mockSwalFire).toHaveBeenCalled())
    // Página ainda renderiza conteúdo — não navega para outra rota
    const paymentNavCalls = mockNavigate.mock.calls.filter(
      ([route]) => route !== '/checkout',
    )
    expect(paymentNavCalls).toHaveLength(0)
  })
})

describe('Cleanup do polling ao desmontar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('aborta polling ao desmontar o componente (pollingAbortRef.abort())', async () => {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    const abortSpy = vi.fn()
    const origAbortController = globalThis.AbortController
    class MockAbortController {
      signal = { aborted: false, addEventListener: vi.fn() }
      abort = abortSpy
    }
    globalThis.AbortController = MockAbortController as unknown as typeof AbortController

    const confirmPaymentMock = vi.fn().mockResolvedValue({ error: null })
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: confirmPaymentMock,
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })
    // GET nunca resolve — polling fica bloqueado
    mockGet.mockReturnValue(new Promise(() => {}))

    const { unmount } = renderPayment()
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))
    fireEvent.click(screen.getByRole('button', { name: /confirmar pagamento/i }))

    unmount()
    expect(abortSpy).toHaveBeenCalled()

    globalThis.AbortController = origAbortController
  })

  it('polling abortado não navega após unmount', async () => {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: vi.fn().mockResolvedValue({ error: null }),
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })
    mockGet.mockReturnValue(new Promise(() => {}))

    const { unmount } = renderPayment()
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))
    fireEvent.click(screen.getByRole('button', { name: /confirmar pagamento/i }))

    unmount()
    // navegar para rotas de resultado não deve ter ocorrido após unmount
    const resultNavCalls = mockNavigate.mock.calls.filter(
      ([route]) =>
        route === '/payment/success' ||
        route === '/payment/failed' ||
        route === '/payment/processing',
    )
    expect(resultNavCalls).toHaveLength(0)
  })
})

// Nota: os testes de polling usam timers REAIS com respostas terminais imediatas.
// O loop de polling só aguarda o setTimeout de 2500ms entre tentativas quando o
// status ainda não é terminal — com status terminal na primeira resposta, o loop
// resolve imediatamente sem necessidade de fake timers (que interferem com waitFor).
describe('Polling — consequências do resultado', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  async function setupAndTriggerPolling(getStatusResult: string) {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: vi.fn().mockResolvedValue({ error: null }),
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    // Configura mocks em ordem: createOrder, createIntent, status, shipments
    mockGet.mockResolvedValueOnce({ data: { status: getStatusResult } })
    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })
      .mockResolvedValue({ data: {} })

    renderPayment()
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))
    fireEvent.click(screen.getByRole('button', { name: /confirmar pagamento/i }))
  }

  it('navega para /payment/success com state.orderId quando resultado é "succeeded"', async () => {
    await setupAndTriggerPolling('succeeded')
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        '/payment/success',
        expect.objectContaining({ state: expect.objectContaining({ orderId: mockOrderCreateResponse.id }) }),
      )
    }, { timeout: 3000 })
  })

  it('dispara POST /logistics/shipments/create/ de forma não-bloqueante após "succeeded"', async () => {
    await setupAndTriggerPolling('succeeded')
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/payment/success', expect.anything()), { timeout: 3000 })
    expect(mockPost).toHaveBeenCalledWith(
      '/logistics/shipments/create/',
      expect.objectContaining({ order_id: mockOrderCreateResponse.id }),
    )
  })

  it('não bloqueia navegação se /logistics/shipments/create/ falhar', async () => {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: vi.fn().mockResolvedValue({ error: null }),
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    mockGet.mockResolvedValueOnce({ data: { status: 'succeeded' } })
    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })
      .mockRejectedValue(new Error('Shipment error'))

    renderPayment()
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))
    fireEvent.click(screen.getByRole('button', { name: /confirmar pagamento/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/payment/success', expect.anything())
    }, { timeout: 3000 })
  })

  it('navega para /payment/failed quando resultado é "failed"', async () => {
    await setupAndTriggerPolling('failed')
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/payment/failed')
    }, { timeout: 3000 })
  })

  it('navega para /payment/failed quando resultado é "cancelled"', async () => {
    await setupAndTriggerPolling('cancelled')
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/payment/failed')
    }, { timeout: 3000 })
  })

  // Nota: o teste de "timeout" ativa fake timers APÓS o componente estar montado
  // (com timers reais) para evitar conflito com waitFor interno do RTL.
  it('navega para /payment/processing com state.orderId quando resultado é "timeout"', async () => {
    const { useStripe, useElements } = await import('@stripe/react-stripe-js')
    ;(useStripe as ReturnType<typeof vi.fn>).mockReturnValue({
      confirmPayment: vi.fn().mockResolvedValue({ error: null }),
    })
    ;(useElements as ReturnType<typeof vi.fn>).mockReturnValue({})

    mockGet.mockResolvedValue({ data: { status: 'pending' } })
    mockPost
      .mockResolvedValueOnce({ data: mockOrderCreateResponse })
      .mockResolvedValueOnce({ data: mockPaymentIntentResponse })
      .mockResolvedValue({ data: {} })

    renderPayment()
    // Usa timers reais para montar o componente
    await waitFor(() => screen.getByText('Pedido criado. Escolha como pagar.'))
    fireEvent.click(screen.getByRole('button', { name: /continuar para pagamento/i }))
    await waitFor(() => screen.getByTestId('payment-element'))

    // Ativa fake timers somente após componente estar pronto
    vi.useFakeTimers()
    try {
      fireEvent.click(screen.getByRole('button', { name: /confirmar pagamento/i }))

      for (let i = 0; i < 14; i++) {
        await vi.advanceTimersByTimeAsync(2500)
      }

      expect(mockNavigate).toHaveBeenCalledWith(
        '/payment/processing',
        expect.objectContaining({ state: expect.objectContaining({ orderId: mockOrderCreateResponse.id }) }),
      )
    } finally {
      vi.useRealTimers()
    }
  })
})
