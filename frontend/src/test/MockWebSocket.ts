/**
 * MockWebSocket — reusable test helper for WebSocket-based hooks.
 *
 * Usage in tests:
 *   import { MockWebSocket, getLastWsInstance } from '@/test/MockWebSocket';
 *
 *   beforeEach(() => { vi.stubGlobal('WebSocket', MockWebSocket); });
 *   afterEach(() => { MockWebSocket.reset(); });
 *
 *   const ws = getLastWsInstance();
 *   ws.simulateOpen();
 *   ws.simulateMessage({ type: 'unread_count', count: 3 });
 *   ws.simulateClose(1006);
 */

export class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState: number = MockWebSocket.CONNECTING;

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  readonly sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    this.simulateClose(code, reason);
  }

  // ── Helpers for tests ──────────────────────────────────────────────

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  simulateMessage(data: unknown) {
    const event = new MessageEvent('message', {
      data: JSON.stringify(data),
    });
    this.onmessage?.(event);
  }

  simulateClose(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    const event = new CloseEvent('close', { code, reason, wasClean: code === 1000 });
    this.onclose?.(event);
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }

  static reset() {
    MockWebSocket.instances = [];
  }
}

export function getLastWsInstance(): MockWebSocket {
  const last = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  if (!last) throw new Error('No MockWebSocket instance found — was the hook mounted?');
  return last;
}
