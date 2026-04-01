import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import React from 'react'

// ── Mocks de módulos — ANTES dos imports de componentes ──────────────────────

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockClearCart = vi.fn()
vi.mock('@/contexts/CartContext', async () => {
  const actual = await vi.importActual<typeof import('@/contexts/CartContext')>('@/contexts/CartContext')
  return {
    ...actual,
    useCart: () => ({
      items: [],
      totalItems: 0,
      addToCart: vi.fn(),
      removeFromCart: vi.fn(),
      updateQuantity: vi.fn(),
      clearCart: mockClearCart,
    }),
  }
})

// ── Imports de componentes APÓS os mocks ─────────────────────────────────────

import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PaymentSuccess } from '../PaymentSuccess'
import { PaymentFailed } from '../PaymentFailed'
import { PaymentProcessing } from '../PaymentProcessing'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderWithRouter(
  component: React.ReactElement,
  state: unknown = null,
  path = '/payment/success',
) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: path, state }]}>
      {component}
    </MemoryRouter>,
  )
}

// ── Testes ────────────────────────────────────────────────────────────────────

describe('PaymentSuccess', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('chama clearCart() exatamente uma vez ao montar', () => {
    renderWithRouter(<PaymentSuccess />, { orderId: 101 })
    expect(mockClearCart).toHaveBeenCalledTimes(1)
  })

  it('exibe o orderId quando presente no location.state', () => {
    renderWithRouter(<PaymentSuccess />, { orderId: 101 })
    expect(screen.getByText(/#101/)).toBeInTheDocument()
  })

  it('não exibe orderId quando undefined no location.state', () => {
    renderWithRouter(<PaymentSuccess />, {})
    expect(screen.queryByText(/#\d+/)).not.toBeInTheDocument()
  })

  it('botão para ver pedidos navega para /mypurchase', () => {
    renderWithRouter(<PaymentSuccess />, { orderId: 101 })
    // Botão "Ver meus pedidos" só aparece quando orderId está presente
    const btn = screen.getByRole('button', { name: /ver meus pedidos/i })
    fireEvent.click(btn)
    expect(mockNavigate).toHaveBeenCalledWith('/mypurchase')
  })
})

describe('PaymentFailed', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('botão "Tentar novamente" navega para /checkout — NÃO para /payment', () => {
    renderWithRouter(<PaymentFailed />, null, '/payment/failed')
    const btn = screen.getByRole('button', { name: /tentar novamente/i })
    fireEvent.click(btn)
    expect(mockNavigate).toHaveBeenCalledWith('/checkout')
    expect(mockNavigate).not.toHaveBeenCalledWith('/payment')
  })

  it('não chama clearCart() — carrinho permanece para nova tentativa', () => {
    renderWithRouter(<PaymentFailed />, null, '/payment/failed')
    expect(mockClearCart).not.toHaveBeenCalled()
  })
})

describe('PaymentProcessing', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('exibe orderId quando presente no location.state', () => {
    renderWithRouter(<PaymentProcessing />, { orderId: 202 }, '/payment/processing')
    expect(screen.getByText(/#202/)).toBeInTheDocument()
  })

  it('botão para acompanhar pedido navega para /mypurchase', () => {
    renderWithRouter(<PaymentProcessing />, { orderId: 202 }, '/payment/processing')
    // Botão "Ver meus pedidos" só aparece quando orderId está presente
    const btn = screen.getByRole('button', { name: /ver meus pedidos/i })
    fireEvent.click(btn)
    expect(mockNavigate).toHaveBeenCalledWith('/mypurchase')
  })
})
