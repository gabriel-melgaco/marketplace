/**
 * Tests for src/utils/confirmDialog.ts
 *
 * Strategy: confirmDialog is a thin wrapper around SweetAlert2's Swal.fire().
 * We mock Swal entirely to control what the dialog "returns" without opening
 * any actual DOM overlay, keeping tests fast and deterministic.
 *
 * Risk level: MEDIUM
 *   - Used to guard irreversible delete operations throughout the app.
 *   - A bug here (always-true or always-false) silently deletes data or blocks
 *     users from ever deleting anything.
 *
 * Coverage matrix
 *   Happy path   : user clicks confirm  → returns true
 *   Happy path   : user clicks cancel   → returns false
 *   Happy path   : user presses Escape  → returns false (isDismissed, not isConfirmed)
 *   Edge cases   : custom options are forwarded to Swal
 *   Edge cases   : default options are applied when no arguments are passed
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Hoist the mock so it is evaluated before any import resolution.
vi.mock("sweetalert2", () => ({
  default: {
    fire: vi.fn(),
  },
}));

import Swal from "sweetalert2";
import { confirmDelete } from "../confirmDialog";

const mockFire = Swal.fire as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── Helper ──────────────────────────────────────────────────────────────────

function stubSwal(isConfirmed: boolean) {
  mockFire.mockResolvedValueOnce({ isConfirmed });
}

// ─── Happy path ──────────────────────────────────────────────────────────────

describe("confirmDelete - return value", () => {
  it("returns true when user confirms", async () => {
    stubSwal(true);
    const result = await confirmDelete();
    expect(result).toBe(true);
  });

  it("returns false when user cancels", async () => {
    stubSwal(false);
    const result = await confirmDelete();
    expect(result).toBe(false);
  });

  it("returns false when dialog is dismissed via Escape key", async () => {
    // Escape/backdrop click sets isConfirmed to false in SweetAlert2
    mockFire.mockResolvedValueOnce({ isConfirmed: false, isDismissed: true });
    const result = await confirmDelete();
    expect(result).toBe(false);
  });
});

// ─── Default options ──────────────────────────────────────────────────────────

describe("confirmDelete - default Swal options", () => {
  it("calls Swal.fire with the correct default title and text", async () => {
    stubSwal(true);
    await confirmDelete();

    expect(mockFire).toHaveBeenCalledOnce();
    const [options] = mockFire.mock.calls[0];
    expect(options.title).toBe("Excluir anúncio?");
    expect(options.text).toBe("Esta ação não pode ser desfeita.");
  });

  it("uses 'warning' icon by default", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.icon).toBe("warning");
  });

  it("shows a cancel button by default", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.showCancelButton).toBe(true);
  });

  it("defaults confirm button text to 'Sim, excluir'", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.confirmButtonText).toBe("Sim, excluir");
  });

  it("has cancel button text as 'Cancelar'", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.cancelButtonText).toBe("Cancelar");
  });

  it("uses red confirm button color (#ef4444)", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.confirmButtonColor).toBe("#ef4444");
  });

  it("reverses button order so cancel appears first", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.reverseButtons).toBe(true);
  });

  it("focuses cancel button by default (safe default against accidental delete)", async () => {
    stubSwal(false);
    await confirmDelete();
    const [options] = mockFire.mock.calls[0];
    expect(options.focusCancel).toBe(true);
  });
});

// ─── Custom options ────────────────────────────────────────────────────────────

describe("confirmDelete - custom options override defaults", () => {
  it("uses custom title when provided", async () => {
    stubSwal(true);
    await confirmDelete({ title: "Remover imagem?" });
    const [options] = mockFire.mock.calls[0];
    expect(options.title).toBe("Remover imagem?");
  });

  it("uses custom text when provided", async () => {
    stubSwal(true);
    await confirmDelete({ text: "A imagem será removida permanentemente." });
    const [options] = mockFire.mock.calls[0];
    expect(options.text).toBe("A imagem será removida permanentemente.");
  });

  it("uses custom confirmButtonText when provided", async () => {
    stubSwal(true);
    await confirmDelete({ confirmButtonText: "Sim, remover" });
    const [options] = mockFire.mock.calls[0];
    expect(options.confirmButtonText).toBe("Sim, remover");
  });

  it("falls back to defaults for missing custom options", async () => {
    stubSwal(false);
    // Only override title — text and confirmButtonText should stay default
    await confirmDelete({ title: "Cancelar pedido?" });
    const [options] = mockFire.mock.calls[0];
    expect(options.text).toBe("Esta ação não pode ser desfeita.");
    expect(options.confirmButtonText).toBe("Sim, excluir");
  });

  it("uses all three custom options simultaneously", async () => {
    stubSwal(true);
    await confirmDelete({
      title: "Desativar anúncio?",
      text: "O anúncio ficará oculto para compradores.",
      confirmButtonText: "Sim, desativar",
    });
    const [options] = mockFire.mock.calls[0];
    expect(options.title).toBe("Desativar anúncio?");
    expect(options.text).toBe("O anúncio ficará oculto para compradores.");
    expect(options.confirmButtonText).toBe("Sim, desativar");
  });
});

// ─── Async correctness ─────────────────────────────────────────────────────────

describe("confirmDelete - async behaviour", () => {
  it("awaits Swal.fire before returning", async () => {
    let resolved = false;
    mockFire.mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(() => {
            resolved = true;
            resolve({ isConfirmed: true });
          }, 0),
        ),
    );

    const promise = confirmDelete();
    // Has not resolved yet before the micro-task queue drains
    expect(resolved).toBe(false);
    const result = await promise;
    expect(resolved).toBe(true);
    expect(result).toBe(true);
  });

  it("is callable multiple times independently", async () => {
    mockFire
      .mockResolvedValueOnce({ isConfirmed: true })
      .mockResolvedValueOnce({ isConfirmed: false });

    expect(await confirmDelete()).toBe(true);
    expect(await confirmDelete()).toBe(false);
    expect(mockFire).toHaveBeenCalledTimes(2);
  });
});
