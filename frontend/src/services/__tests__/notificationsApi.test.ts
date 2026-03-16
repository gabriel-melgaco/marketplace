import { describe, it, expect, vi, beforeEach } from 'vitest';

// ─── Mock @/api/axios (hoisted so factory runs before imports) ────────────────

const { mockGet, mockPost, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
}));

vi.mock('@/api/axios', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
  },
}));

import { notificationsApi } from '../notificationsApi';

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── notificationsApi.list ────────────────────────────────────────────────────

describe('notificationsApi.list', () => {
  const mockResponse = {
    count: 5,
    next: null,
    previous: null,
    results: [],
  };

  it('calls GET /notifications/ with page: 1 when called with no params', async () => {
    mockGet.mockResolvedValueOnce({ data: mockResponse });

    await notificationsApi.list();

    expect(mockGet).toHaveBeenCalledOnce();
    const [url, config] = mockGet.mock.calls[0];
    expect(url).toBe('/notifications/');
    expect(config.params.page).toBe(1);
  });

  it('passes page: 2 when called with { page: 2 }', async () => {
    mockGet.mockResolvedValueOnce({ data: mockResponse });

    await notificationsApi.list({ page: 2 });

    const [, config] = mockGet.mock.calls[0];
    expect(config.params.page).toBe(2);
  });

  it('passes read: "true" when isRead is true', async () => {
    mockGet.mockResolvedValueOnce({ data: mockResponse });

    await notificationsApi.list({ isRead: true });

    const [, config] = mockGet.mock.calls[0];
    expect(config.params.read).toBe('true');
  });

  it('passes read: "false" when isRead is false', async () => {
    mockGet.mockResolvedValueOnce({ data: mockResponse });

    await notificationsApi.list({ isRead: false });

    const [, config] = mockGet.mock.calls[0];
    expect(config.params.read).toBe('false');
  });

  it('omits the read param entirely when isRead is not provided', async () => {
    mockGet.mockResolvedValueOnce({ data: mockResponse });

    await notificationsApi.list();

    const [, config] = mockGet.mock.calls[0];
    expect(Object.prototype.hasOwnProperty.call(config.params, 'read')).toBe(false);
  });

  it('returns the paginated response data', async () => {
    const expectedResponse = {
      count: 3,
      next: 'http://api/notifications/?page=2',
      previous: null,
      results: [{ id: 'n1' }],
    };
    mockGet.mockResolvedValueOnce({ data: expectedResponse });

    const result = await notificationsApi.list();

    expect(result).toEqual(expectedResponse);
  });

  it('propagates network errors', async () => {
    const networkError = new Error('Network Error');
    mockGet.mockRejectedValueOnce(networkError);

    await expect(notificationsApi.list()).rejects.toThrow('Network Error');
  });
});

// ─── notificationsApi.markAsRead ─────────────────────────────────────────────

describe('notificationsApi.markAsRead', () => {
  it('calls POST /notifications/{id}/read/', async () => {
    const notification = { id: 'abc', is_read: true };
    mockPost.mockResolvedValueOnce({ data: notification });

    const result = await notificationsApi.markAsRead('abc');

    expect(mockPost).toHaveBeenCalledWith('/notifications/abc/read/');
    expect(result).toEqual(notification);
  });

  it('propagates errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Server Error'));

    await expect(notificationsApi.markAsRead('abc')).rejects.toThrow('Server Error');
  });
});

// ─── notificationsApi.markAllAsRead ──────────────────────────────────────────

describe('notificationsApi.markAllAsRead', () => {
  it('calls POST /notifications/read-all/', async () => {
    mockPost.mockResolvedValueOnce({ data: { marked: 2 } });

    const result = await notificationsApi.markAllAsRead();

    expect(mockPost).toHaveBeenCalledWith('/notifications/read-all/');
    expect(result).toEqual({ marked: 2 });
  });

  it('propagates errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Server Error'));

    await expect(notificationsApi.markAllAsRead()).rejects.toThrow('Server Error');
  });
});

// ─── notificationsApi.getUnreadCount ─────────────────────────────────────────

describe('notificationsApi.getUnreadCount', () => {
  it('calls GET /notifications/unread-count/ and returns the number', async () => {
    mockGet.mockResolvedValueOnce({ data: { count: 3 } });

    const result = await notificationsApi.getUnreadCount();

    expect(mockGet).toHaveBeenCalledWith('/notifications/unread-count/');
    // Must return the number, not the wrapper object
    expect(result).toBe(3);
    expect(typeof result).toBe('number');
  });

  it('returns 0 when count is 0', async () => {
    mockGet.mockResolvedValueOnce({ data: { count: 0 } });

    const result = await notificationsApi.getUnreadCount();

    expect(result).toBe(0);
  });

  it('propagates errors', async () => {
    mockGet.mockRejectedValueOnce(new Error('Timeout'));

    await expect(notificationsApi.getUnreadCount()).rejects.toThrow('Timeout');
  });
});

// ─── notificationsApi.getPreferences ─────────────────────────────────────────

describe('notificationsApi.getPreferences', () => {
  it('calls GET /notifications/preferences/', async () => {
    const prefs = { order_created_ws: true, order_created_email: false };
    mockGet.mockResolvedValueOnce({ data: prefs });

    const result = await notificationsApi.getPreferences();

    expect(mockGet).toHaveBeenCalledWith('/notifications/preferences/');
    expect(result).toEqual(prefs);
  });

  it('propagates errors', async () => {
    mockGet.mockRejectedValueOnce(new Error('Forbidden'));

    await expect(notificationsApi.getPreferences()).rejects.toThrow('Forbidden');
  });
});

// ─── notificationsApi.updatePreferences ──────────────────────────────────────

describe('notificationsApi.updatePreferences', () => {
  it('calls PATCH /notifications/preferences/ with the partial payload', async () => {
    const partial = { order_created_ws: false };
    const updatedPrefs = { order_created_ws: false, order_created_email: true };
    mockPatch.mockResolvedValueOnce({ data: updatedPrefs });

    const result = await notificationsApi.updatePreferences(partial);

    expect(mockPatch).toHaveBeenCalledWith('/notifications/preferences/', partial);
    expect(result).toEqual(updatedPrefs);
  });

  it('sends only the fields provided in the partial', async () => {
    const partial = { new_message_email: true };
    mockPatch.mockResolvedValueOnce({ data: partial });

    await notificationsApi.updatePreferences(partial);

    const [, payload] = mockPatch.mock.calls[0];
    expect(payload).toStrictEqual({ new_message_email: true });
    // No extra fields leaked
    expect(Object.keys(payload)).toHaveLength(1);
  });

  it('propagates errors', async () => {
    mockPatch.mockRejectedValueOnce(new Error('Validation Error'));

    await expect(
      notificationsApi.updatePreferences({ order_created_ws: false })
    ).rejects.toThrow('Validation Error');
  });
});
