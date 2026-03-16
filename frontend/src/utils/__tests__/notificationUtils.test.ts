import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import {
  formatNotificationDate,
  getNotificationMeta,
  NOTIFICATION_TYPE_GROUPS,
} from '../notificationUtils';
import type { NotificationType } from '@/types/notifications';

// ─── formatNotificationDate ──────────────────────────────────────────────────

describe('formatNotificationDate', () => {
  const NOW = new Date('2024-06-15T12:00:00Z');

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "agora mesmo" for a timestamp less than 1 minute ago', () => {
    const thirtySecondsAgo = new Date(NOW.getTime() - 30_000).toISOString();
    expect(formatNotificationDate(thirtySecondsAgo)).toBe('agora mesmo');
  });

  it('returns "agora mesmo" for a timestamp exactly 0 ms ago', () => {
    expect(formatNotificationDate(NOW.toISOString())).toBe('agora mesmo');
  });

  it('returns "há 1 min" for exactly 1 minute ago', () => {
    const oneMinAgo = new Date(NOW.getTime() - 60_000).toISOString();
    expect(formatNotificationDate(oneMinAgo)).toBe('há 1 min');
  });

  it('returns "há 59 min" for 59 minutes ago', () => {
    const fiftyNineMinAgo = new Date(NOW.getTime() - 59 * 60_000).toISOString();
    expect(formatNotificationDate(fiftyNineMinAgo)).toBe('há 59 min');
  });

  it('returns "há 1h" for exactly 1 hour ago', () => {
    const oneHourAgo = new Date(NOW.getTime() - 3_600_000).toISOString();
    expect(formatNotificationDate(oneHourAgo)).toBe('há 1h');
  });

  it('returns "há 23h" for 23 hours ago', () => {
    const twentyThreeHoursAgo = new Date(NOW.getTime() - 23 * 3_600_000).toISOString();
    expect(formatNotificationDate(twentyThreeHoursAgo)).toBe('há 23h');
  });

  it('returns "há 1d" for exactly 1 day ago', () => {
    const oneDayAgo = new Date(NOW.getTime() - 86_400_000).toISOString();
    expect(formatNotificationDate(oneDayAgo)).toBe('há 1d');
  });

  it('returns "há 6d" for 6 days ago', () => {
    const sixDaysAgo = new Date(NOW.getTime() - 6 * 86_400_000).toISOString();
    expect(formatNotificationDate(sixDaysAgo)).toBe('há 6d');
  });

  it('returns a localized date string for 7 days ago (uses toLocaleDateString)', () => {
    const sevenDaysAgo = new Date(NOW.getTime() - 7 * 86_400_000).toISOString();
    const result = formatNotificationDate(sevenDaysAgo);
    // Should NOT be relative — must be formatted date string
    expect(result).not.toMatch(/^há/);
    expect(result).not.toBe('agora mesmo');
    // Verify it matches toLocaleDateString output
    const expected = new Date(sevenDaysAgo).toLocaleDateString('pt-BR', {
      day: 'numeric',
      month: 'short',
    });
    expect(result).toBe(expected);
  });

  it('accepts an optional now parameter and uses it instead of the real clock', () => {
    const customNow = new Date('2024-06-15T10:00:00Z');
    const thirtyMinBeforeCustomNow = new Date(customNow.getTime() - 30 * 60_000).toISOString();
    // With customNow: 30 min ago → "há 30 min"
    expect(formatNotificationDate(thirtyMinBeforeCustomNow, customNow)).toBe('há 30 min');
    // With real clock (NOW = 12:00) the same timestamp is 150 min → "há 2h"
    expect(formatNotificationDate(thirtyMinBeforeCustomNow)).toBe('há 2h');
  });
});

// ─── getNotificationMeta ─────────────────────────────────────────────────────

describe('getNotificationMeta', () => {
  it('returns correct label and colorClass for a known type', () => {
    const meta = getNotificationMeta('order_created');
    expect(meta.label).toBe('Pedido Criado');
    expect(meta.colorClass).toBe('text-blue-600');
  });

  it('returns label "Notificação" for an unknown type', () => {
    const meta = getNotificationMeta('totally_unknown_type');
    expect(meta.label).toBe('Notificação');
    expect(meta.colorClass).toBe('text-gray-600');
  });

  it('unknown type has no route function', () => {
    const meta = getNotificationMeta('totally_unknown_type');
    expect(meta.route).toBeUndefined();
  });

  it('new_message route returns /chats/${chat_id}', () => {
    const meta = getNotificationMeta('new_message');
    expect(meta.route).toBeDefined();
    expect(meta.route!({ chat_id: '42' })).toBe('/chats/42');
  });

  it('listing_blocked route returns /products/${listing_id}', () => {
    const meta = getNotificationMeta('listing_blocked');
    expect(meta.route).toBeDefined();
    expect(meta.route!({ listing_id: 'abc123' })).toBe('/products/abc123');
  });

  it('seller_verified route returns /seller/dashboard', () => {
    const meta = getNotificationMeta('seller_verified');
    expect(meta.route).toBeDefined();
    expect(meta.route!({})).toBe('/seller/dashboard');
  });

  it('listing_created route returns /products/${listing_id}', () => {
    const meta = getNotificationMeta('listing_created');
    expect(meta.route!({ listing_id: 'xyz789' })).toBe('/products/xyz789');
  });

  it('order_created route returns /mypurchase', () => {
    const meta = getNotificationMeta('order_created');
    expect(meta.route!({})).toBe('/mypurchase');
  });
});

// ─── NOTIFICATION_TYPE_GROUPS ─────────────────────────────────────────────────

describe('NOTIFICATION_TYPE_GROUPS', () => {
  const ALL_TYPES: NotificationType[] = [
    'order_created',
    'order_status_changed',
    'payment_confirmed',
    'payment_failed',
    'dispute_opened',
    'shipment_created',
    'shipment_status_updated',
    'delivery_scheduled',
    'delivery_confirmed',
    'new_message',
    'seller_verified',
    'listing_blocked',
    'listing_created',
  ];

  it('has exactly 13 total NotificationType values across all groups', () => {
    const flat = NOTIFICATION_TYPE_GROUPS.flatMap((g) => g.types);
    expect(flat).toHaveLength(13);
  });

  it('includes every NotificationType exactly once', () => {
    const flat = NOTIFICATION_TYPE_GROUPS.flatMap((g) => g.types);
    ALL_TYPES.forEach((type) => {
      const occurrences = flat.filter((t) => t === type).length;
      expect(occurrences).toBe(1);
    });
  });

  it('contains no duplicate types within or across groups', () => {
    const flat = NOTIFICATION_TYPE_GROUPS.flatMap((g) => g.types);
    const unique = new Set(flat);
    expect(unique.size).toBe(flat.length);
  });

  it('has 5 group entries', () => {
    expect(NOTIFICATION_TYPE_GROUPS).toHaveLength(5);
  });

  it('groups have the expected labels', () => {
    const labels = NOTIFICATION_TYPE_GROUPS.map((g) => g.groupLabel);
    expect(labels).toContain('Pedidos');
    expect(labels).toContain('Pagamentos');
    expect(labels).toContain('Envio e Entrega');
    expect(labels).toContain('Mensagens');
    expect(labels).toContain('Conta e Anúncios');
  });
});
