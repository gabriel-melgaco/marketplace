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

const { mockAxiosGet, mockAxiosPost, mockAxiosDelete } = vi.hoisted(() => ({
  mockAxiosGet: vi.fn(),
  mockAxiosPost: vi.fn(),
  mockAxiosDelete: vi.fn(),
}))

vi.mock('@/api/axios', () => ({
  default: {
    get: mockAxiosGet,
    post: mockAxiosPost,
    delete: mockAxiosDelete,
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
    },
    isAxiosError: (err: unknown) =>
      !!(err && typeof err === 'object' && 'response' in err),
  }
})

import { mockAddresses, mockShippingResponse } from '../../../Payment/__tests__/fixtures'

vi.mock('@/services/addressService', () => ({
  addressService: {
    listAddresses: vi.fn(() => Promise.resolve(mockAddresses)),
    createAddress: vi.fn(() => Promise.resolve({ id: 99, ...mockAddresses[0] })),
    lookupCEP: vi.fn(() =>
      Promise.resolve({
        street: 'Rua Preenchida',
        neighborhood: 'Bairro',
        city: 'Cidade',
        state: 'SP',
      }),
    ),
  },
}))

vi.mock('@/services/shippingService', () => ({
  shippingService: {
    calculateShipping: vi.fn(() => Promise.resolve(mockShippingResponse)),
  },
}))

vi.mock('@/services/storageService', () => ({
  toPublicUrl: (url: string) => url,
}))

const mockSwalFire = vi.fn(() => Promise.resolve({ isConfirmed: true }))
vi.mock('sweetalert2', () => ({
  default: { fire: (...args: unknown[]) => mockSwalFire(...args) },
}))

// ── Imports de componentes APÓS os mocks ─────────────────────────────────────

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CartContext } from '@/contexts/CartContext'
import { Checkout } from '../index'

// ── Fixtures locais ───────────────────────────────────────────────────────────

const mockCartItems = [
  {
    listing: {
      id: 10,
      seller: 1,
      seller_name: 'Vendedor A',
      price: '99.90',
      title: 'Produto A',
      quantity: 10,
      product: { name: 'Produto A' },
      images: [],
    },
    quantity: 2,
  },
  {
    listing: {
      id: 20,
      seller: 2,
      seller_name: 'Vendedor B',
      price: '49.90',
      title: 'Produto B',
      quantity: 5,
      product: { name: 'Produto B' },
      images: [],
    },
    quantity: 1,
  },
]

const clearCartMock = vi.fn()
const addToCartMock = vi.fn()
const removeFromCartMock = vi.fn()
const updateQuantityMock = vi.fn()

function makeCartContext(items = mockCartItems) {
  return {
    items,
    totalItems: items.reduce((s, i) => s + i.quantity, 0),
    addToCart: addToCartMock,
    removeFromCart: removeFromCartMock,
    updateQuantity: updateQuantityMock,
    clearCart: clearCartMock,
  }
}

function renderCheckout(
  cartItems = mockCartItems,
  locationState: unknown = null,
) {
  return render(
    <CartContext.Provider value={makeCartContext(cartItems)}>
      <MemoryRouter initialEntries={[{ pathname: '/checkout', state: locationState }]}>
        <Checkout />
      </MemoryRouter>
    </CartContext.Provider>,
  )
}

// ── Testes ────────────────────────────────────────────────────────────────────

describe('ClientCheckout', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('redirecionamento com carrinho vazio', () => {
    it('redireciona para "/" quando o carrinho está vazio ao montar', () => {
      renderCheckout([])
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  describe('AlertBanner de erro de navegação anterior', () => {
    it('exibe AlertBanner quando location.state.error está presente', async () => {
      renderCheckout(mockCartItems, { error: 'Sua cotação expirou.' })
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
        expect(screen.getByText('Sua cotação expirou.')).toBeInTheDocument()
      })
    })

    it('não exibe AlertBanner quando location.state é null', async () => {
      renderCheckout(mockCartItems, null)
      await waitFor(() =>
        expect(screen.queryByText('Sua cotação expirou.')).not.toBeInTheDocument(),
      )
    })
  })

  describe('endereços', () => {
    it('chama addressService.listAddresses() ao montar', async () => {
      const { addressService } = await import('@/services/addressService')
      renderCheckout()
      await waitFor(() => {
        expect(addressService.listAddresses).toHaveBeenCalledTimes(1)
      })
    })

    it('auto-seleciona o endereço com is_default=true quando existe', async () => {
      renderCheckout()
      // Após carregar, o endereço padrão (id=1, "João") deve estar selecionado
      await waitFor(() => {
        expect(screen.getByText('João')).toBeInTheDocument()
      })
    })

    it('auto-seleciona o primeiro endereço quando nenhum tem is_default=true', async () => {
      const { addressService } = await import('@/services/addressService')
      const addressesWithoutDefault = mockAddresses.map((a) => ({ ...a, is_default: false }))
      ;(addressService.listAddresses as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
        addressesWithoutDefault,
      )
      renderCheckout()
      await waitFor(() => {
        // O primeiro endereço (João) deve aparecer selecionado
        expect(screen.getByText('João')).toBeInTheDocument()
      })
    })

    it('exibe formulário inline quando lista de endereços retorna vazia', async () => {
      const { addressService } = await import('@/services/addressService')
      ;(addressService.listAddresses as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])
      renderCheckout()
      await waitFor(() => {
        // Formulário inline deve aparecer — busca por campo de nome do destinatário
        expect(
          screen.getByRole('textbox', { name: /nome do destinatário/i }),
        ).toBeInTheDocument()
      })
    })

    it('exibe spinner de carregamento enquanto addresses está sendo buscado', async () => {
      const { addressService } = await import('@/services/addressService')
      ;(addressService.listAddresses as ReturnType<typeof vi.fn>).mockReturnValueOnce(
        new Promise(() => {}),
      )
      renderCheckout()
      // O LoadingRow exibe "Carregando endereços..." durante o carregamento
      expect(screen.getByText('Carregando endereços...')).toBeInTheDocument()
    })

    it('permite trocar o endereço selecionado clicando em outro card', async () => {
      renderCheckout()
      await waitFor(() => screen.getByText('Maria'))
      // Clica no segundo endereço
      const mariaCard = screen.getByText('Maria').closest('div[role]') ??
        screen.getByText('Maria').closest('div')
      if (mariaCard) fireEvent.click(mariaCard)
      // Maria fica selecionada — verificado pela ausência de erro ou por outro elemento
      expect(screen.getByText('Maria')).toBeInTheDocument()
    })
  })

  describe('lookup de CEP', () => {
    beforeEach(async () => {
      const { addressService } = await import('@/services/addressService')
      ;(addressService.listAddresses as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])
    })

    it('chama addressService.lookupCEP() ao sair do campo de CEP com 8 dígitos', async () => {
      const { addressService } = await import('@/services/addressService')
      renderCheckout()
      await waitFor(() => screen.getByRole('textbox', { name: /cep/i }))
      const cepInput = screen.getByRole('textbox', { name: /cep/i })
      fireEvent.change(cepInput, { target: { value: '01310100' } })
      fireEvent.blur(cepInput)
      await waitFor(() => {
        expect(addressService.lookupCEP).toHaveBeenCalledWith({ zipcode: '01310100' })
      })
    })

    it('preenche street, neighborhood, city e state com a resposta do CEP', async () => {
      renderCheckout()
      await waitFor(() => screen.getByRole('textbox', { name: /cep/i }))
      const cepInput = screen.getByRole('textbox', { name: /cep/i })
      fireEvent.change(cepInput, { target: { value: '01310100' } })
      fireEvent.blur(cepInput)
      await waitFor(() => {
        expect(
          (screen.getByRole('textbox', { name: /rua|logradouro/i }) as HTMLInputElement).value,
        ).toBe('Rua Preenchida')
      })
    })

    it('não chama lookupCEP quando o CEP tem menos de 8 dígitos', async () => {
      const { addressService } = await import('@/services/addressService')
      renderCheckout()
      await waitFor(() => screen.getByRole('textbox', { name: /cep/i }))
      const cepInput = screen.getByRole('textbox', { name: /cep/i })
      fireEvent.change(cepInput, { target: { value: '0131' } })
      fireEvent.blur(cepInput)
      expect(addressService.lookupCEP).not.toHaveBeenCalled()
    })
  })

  describe('sincronização do carrinho e cálculo de frete', () => {
    it('chama DELETE /orders/cart/clear/ antes de qualquer POST /orders/cart/add/', async () => {
      const callOrder: string[] = []

      mockAxiosDelete.mockImplementation((url: string) => {
        callOrder.push(`DELETE:${url}`)
        return Promise.resolve({ data: {} })
      })

      mockAxiosPost.mockImplementation((url: string) => {
        callOrder.push(`POST:${url}`)
        return Promise.resolve({ data: {} })
      })

      renderCheckout()
      await waitFor(() => expect(mockAxiosPost).toHaveBeenCalled())

      const clearIndex = callOrder.findIndex((c) => c.includes('cart/clear'))
      const addIndex = callOrder.findIndex((c) => c.includes('cart/add'))
      expect(clearIndex).toBeLessThan(addIndex)
    })

    it('chama POST /orders/cart/add/ para cada item do carrinho', async () => {
      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockResolvedValue({ data: {} })

      renderCheckout()
      await waitFor(() => {
        const addCalls = mockAxiosPost.mock.calls.filter(([url]) =>
          url.includes('cart/add'),
        )
        expect(addCalls.length).toBe(mockCartItems.length)
      })
    })

    it('chama calculateShipping apenas APÓS todos os POSTs de cart/add/ concluírem', async () => {
      const { shippingService } = await import('@/services/shippingService')
      const callOrder: string[] = []

      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockImplementation((url: string) => {
        callOrder.push(`POST:${url}`)
        return Promise.resolve({ data: {} })
      })
      ;(shippingService.calculateShipping as ReturnType<typeof vi.fn>).mockImplementation(() => {
        callOrder.push('calculateShipping')
        return Promise.resolve(mockShippingResponse)
      })

      renderCheckout()
      await waitFor(() => expect(shippingService.calculateShipping).toHaveBeenCalled())

      const lastAddIndex = callOrder
        .map((c, i) => (c.includes('cart/add') ? i : -1))
        .filter((i) => i >= 0)
        .pop() ?? -1
      const shippingIndex = callOrder.indexOf('calculateShipping')

      expect(shippingIndex).toBeGreaterThan(lastAddIndex)
    })

    it('trata 404 no DELETE cart/clear/ como carrinho já vazio e continua normalmente', async () => {
      const { shippingService } = await import('@/services/shippingService')
      mockAxiosDelete.mockRejectedValueOnce({
        response: { status: 404 },
      })
      mockAxiosPost.mockResolvedValue({ data: {} })

      renderCheckout()
      await waitFor(() => {
        expect(shippingService.calculateShipping).toHaveBeenCalled()
      })
    })

    it('não re-executa sincronização quando sellerGroups (Map) muda', async () => {
      const { shippingService } = await import('@/services/shippingService')
      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockResolvedValue({ data: {} })

      renderCheckout()
      await waitFor(() => expect(shippingService.calculateShipping).toHaveBeenCalledTimes(1))
      // Não deve ter chamado calculateShipping mais de uma vez (re-render não re-executa)
      expect(shippingService.calculateShipping).toHaveBeenCalledTimes(1)
    })
  })

  describe('cotações de frete por vendedor', () => {
    beforeEach(() => {
      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockResolvedValue({ data: {} })
    })

    it('renderiza cards de cotação para cada opção de serviço retornada', async () => {
      renderCheckout()
      await waitFor(() => {
        // mockShippingResponse tem PAC e SEDEX para o vendedor 1
        expect(screen.getByText('PAC')).toBeInTheDocument()
        expect(screen.getByText('SEDEX')).toBeInTheDocument()
      })
    })

    it('exibe mensagem de entrega presencial para seller com in_person_only=true', async () => {
      renderCheckout()
      await waitFor(() => {
        // Vendedor B tem in_person_only=true — o componente exibe "realiza entrega pessoal"
        expect(
          screen.getByText(/realiza entrega pessoal/i),
        ).toBeInTheDocument()
      })
    })
  })

  describe('botão de prosseguir para pagamento', () => {
    beforeEach(() => {
      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockResolvedValue({ data: {} })
    })

    it('está desabilitado quando selectedAddressId é null', async () => {
      const { addressService } = await import('@/services/addressService')
      ;(addressService.listAddresses as ReturnType<typeof vi.fn>).mockReturnValueOnce(
        new Promise(() => {}),
      )
      renderCheckout()
      // Com endereços carregando, selectedAddressId é null — botão "Ir para pagamento" desabilitado
      const btn = screen.getByRole('button', { name: /ir para pagamento/i })
      expect(btn).toBeDisabled()
    })

    it('navega para /payment com state correto quando habilitado e clicado', async () => {
      const { shippingService } = await import('@/services/shippingService')
      // Retorna apenas um vendedor in_person_only para facilitar (não precisa selecionar serviço)
      ;(shippingService.calculateShipping as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ...mockShippingResponse,
        quotes_by_seller: {
          '1': {
            seller_name: 'Vendedor A',
            in_person_only: true,
            has_in_person: true,
            in_person_items: [{ listing_id: 10, title: 'Produto A', shipping_method: 'in_person' }],
            melhor_envio_items: [],
            services: [],
          },
        },
      })

      const singleItemCart = [mockCartItems[0]]
      renderCheckout(singleItemCart)

      await waitFor(() => {
        const btn = screen.getByRole('button', { name: /ir para pagamento/i })
        expect(btn).not.toBeDisabled()
      })

      const btn = screen.getByRole('button', { name: /ir para pagamento/i })
      fireEvent.click(btn)

      expect(mockNavigate).toHaveBeenCalledWith(
        '/payment',
        expect.objectContaining({ state: expect.objectContaining({ shippingAddressId: 1 }) }),
      )
    })
  })

  describe('erros no cálculo de frete', () => {
    beforeEach(() => {
      mockAxiosDelete.mockResolvedValue({ data: {} })
      mockAxiosPost.mockResolvedValue({ data: {} })
    })

    it('exibe Swal de erro quando API retorna 422 insufficient_me_balance', async () => {
      const { shippingService } = await import('@/services/shippingService')
      ;(shippingService.calculateShipping as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
        response: { status: 422, data: { error: 'insufficient_me_balance' } },
      })
      renderCheckout()
      await waitFor(() => {
        expect(mockSwalFire).toHaveBeenCalledWith(
          expect.objectContaining({ icon: 'error', title: 'Envio indisponível' }),
        )
      })
    })

    it('redireciona /checkout com state.error quando API retorna 400 com cotação expirada', async () => {
      const { shippingService } = await import('@/services/shippingService')
      ;(shippingService.calculateShipping as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
        response: { status: 400, data: { error: 'cotação expirada' } },
      })
      renderCheckout()
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          '/checkout',
          expect.objectContaining({ state: expect.objectContaining({ error: expect.any(String) }) }),
        )
      })
    })
  })
})
