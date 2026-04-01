import { describe, it, expect, vi, beforeEach } from 'vitest';
import { shippingService } from '@/services/shippingService';

// ── Mock axios ────────────────────────────────────────────────────────────────
// vi.hoisted é necessário porque vi.mock() é içado (hoisted) para o topo do
// arquivo pelo plugin do Vitest; sem vi.hoisted, as variáveis não existiriam
// ainda no momento em que a factory do mock é executada.

const { mockPost, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockGet: vi.fn(),
}));

vi.mock('@/api/axios', () => ({
  default: { get: mockGet, post: mockPost, delete: vi.fn() },
}));

// ── Testes ────────────────────────────────────────────────────────────────────

describe('shippingService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('confirmDelivery()', () => {
    it('faz POST para /logistics/shipments/:id/delivered/ com o id correto', async () => {
      mockPost.mockResolvedValueOnce({ data: undefined });
      await shippingService.confirmDelivery(7);
      expect(mockPost).toHaveBeenCalledWith('/logistics/shipments/7/delivered/');
    });

    it('URL usa o shipmentId numérico sem transformação', async () => {
      mockPost.mockResolvedValueOnce({ data: undefined });
      await shippingService.confirmDelivery(42);
      const [url] = mockPost.mock.calls[0];
      expect(url).toBe('/logistics/shipments/42/delivered/');
    });

    it('não envia body na requisição', async () => {
      mockPost.mockResolvedValueOnce({ data: undefined });
      await shippingService.confirmDelivery(7);
      // A chamada deve ter apenas a URL como argumento — sem body
      expect(mockPost).toHaveBeenCalledWith('/logistics/shipments/7/delivered/');
      expect(mockPost.mock.calls[0]).toHaveLength(1);
    });

    it('retorna void em caso de sucesso', async () => {
      mockPost.mockResolvedValueOnce({ data: undefined });
      const result = await shippingService.confirmDelivery(7);
      expect(result).toBeUndefined();
    });

    it('propaga erro da API', async () => {
      mockPost.mockRejectedValueOnce(new Error('Acesso negado'));
      await expect(shippingService.confirmDelivery(7)).rejects.toThrow('Acesso negado');
    });
  });

  describe('calculateShipping()', () => {
    it('faz POST para /logistics/shipping/calculate/ com shipping_address_id no payload', async () => {
      mockPost.mockResolvedValueOnce({
        data: {
          quotes_by_seller: {},
          shipping_address_id: 1,
          total_items: 1,
          total_value: 99.90,
        },
      });
      await shippingService.calculateShipping({ shipping_address_id: 1 });
      expect(mockPost).toHaveBeenCalledWith('/logistics/shipping/calculate/', {
        shipping_address_id: 1,
      });
    });

    it('propaga erro da API', async () => {
      mockPost.mockRejectedValueOnce(new Error('CEP inválido'));
      await expect(
        shippingService.calculateShipping({ shipping_address_id: 1 }),
      ).rejects.toThrow('CEP inválido');
    });
  });

  describe('getOrderShipments()', () => {
    it('faz GET para /logistics/shipments/order/:orderId/', async () => {
      mockGet.mockResolvedValueOnce({ data: { order_id: '101', shipments: [] } });
      await shippingService.getOrderShipments('101');
      expect(mockGet).toHaveBeenCalledWith('/logistics/shipments/order/101/');
    });

    it('usa orderId como string na URL', async () => {
      mockGet.mockResolvedValueOnce({ data: { order_id: '999', shipments: [] } });
      await shippingService.getOrderShipments('999');
      const [url] = mockGet.mock.calls[0];
      expect(url).toBe('/logistics/shipments/order/999/');
    });

    it('propaga erro da API', async () => {
      mockGet.mockRejectedValueOnce(new Error('Pedido não encontrado'));
      await expect(shippingService.getOrderShipments('101')).rejects.toThrow(
        'Pedido não encontrado',
      );
    });
  });

  describe('markAsShipped()', () => {
    it('faz POST para /logistics/shipments/:id/ship/', async () => {
      mockPost.mockResolvedValueOnce({ data: {} });
      await shippingService.markAsShipped(5, 'BR123456789');
      expect(mockPost).toHaveBeenCalledWith(
        '/logistics/shipments/5/ship/',
        expect.objectContaining({ tracking_code: 'BR123456789' }),
      );
    });

    it('inclui tracking_code no body da requisição', async () => {
      mockPost.mockResolvedValueOnce({ data: {} });
      await shippingService.markAsShipped(5, 'XY987654321');
      const [, body] = mockPost.mock.calls[0];
      expect(body).toEqual({ tracking_code: 'XY987654321' });
    });
  });
});
