export const mockCartItems = [
  {
    listing: {
      id: 10,
      seller: 1,
      seller_name: 'Vendedor A',
      price: '99.90',
      title: 'Produto A',
      primary_image: null,
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
      primary_image: null,
    },
    quantity: 1,
  },
]

export const mockAddresses = [
  {
    id: 1,
    recipient_name: 'João',
    recipient_phone: '(11) 99999-9999',
    zipcode: '01310-100',
    street: 'Av. Paulista',
    number: '1000',
    complement: '',
    neighborhood: 'Bela Vista',
    city: 'São Paulo',
    state: 'SP',
    address_type: 'shipping',
    is_shipping_address: true,
    is_default: true,
  },
  {
    id: 2,
    recipient_name: 'Maria',
    recipient_phone: '(11) 88888-8888',
    zipcode: '04501-000',
    street: 'Rua Augusta',
    number: '200',
    complement: '',
    neighborhood: 'Consolação',
    city: 'São Paulo',
    state: 'SP',
    address_type: 'shipping',
    is_shipping_address: true,
    is_default: false,
  },
]

export const mockShippingResponse = {
  quotes_by_seller: {
    '1': {
      seller_name: 'Vendedor A',
      in_person_only: false,
      has_in_person: false,
      in_person_items: [],
      melhor_envio_items: [
        { listing_id: 10, title: 'Produto A', shipping_method: 'melhor_envio' },
      ],
      services: [
        { service_id: 1, name: 'PAC', company: 'Correios', price: 15.90, delivery_time: 7 },
        { service_id: 2, name: 'SEDEX', company: 'Correios', price: 29.90, delivery_time: 2 },
      ],
    },
    '2': {
      seller_name: 'Vendedor B',
      in_person_only: true,
      has_in_person: true,
      in_person_items: [
        { listing_id: 20, title: 'Produto B', shipping_method: 'in_person' },
      ],
      melhor_envio_items: [],
      services: [],
    },
  },
  shipping_address_id: 1,
  total_items: 2,
  total_value: 249.70,
}

export const mockCheckoutState = {
  shippingAddressId: 1,
  selectedServices: { '1': 1 },
  inPersonSellers: ['2'],
  sellerDeliveryMethods: { '1': 'melhor_envio' as const, '2': 'vendor' as const },
  quotesSnapshot: {
    '1': {
      melhor_envio_items: [{ listing_id: 10 }],
      in_person_items: [],
      in_person_only: false,
    },
    '2': {
      melhor_envio_items: [],
      in_person_items: [{ listing_id: 20 }],
      in_person_only: true,
    },
  },
}

export const mockPaymentIntentResponse = {
  payment_id: 42,
  client_secret: 'pi_3abc123_secret_xyz',
  amount: 24990,
  currency: 'brl',
  payment_method: 'credit_card',
}

export const mockOrderCreateResponse = {
  id: 101,
}
