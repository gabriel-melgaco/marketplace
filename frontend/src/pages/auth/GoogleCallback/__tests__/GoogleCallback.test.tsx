/**
 * Tests for src/pages/auth/GoogleCallback/index.tsx
 *
 * Risk level: CRITICAL
 *   - CSRF state validation is the only security barrier preventing an
 *     attacker from injecting a stolen authorisation code into a victim's
 *     session.  Any bypass in the null-handling logic would be a security
 *     regression.
 *   - The "error" query-param branch is the user-visible error path for every
 *     Google-side rejection (access_denied, server_error, etc.).
 *   - The effect must not fire twice; double-invocation would waste the
 *     one-time-use authorisation code, causing an opaque backend error.
 *
 * Fix 2 — CSRF state validation (full null-case matrix)
 * ───────────────────────────────────────────────────────
 * The old guard `if (state && storedState && state !== storedState)` could be
 * bypassed when either value was null/undefined.  The new logic uses an
 * explicit `stateMismatch` variable:
 *
 *   const stateMismatch =
 *     state !== storedState ||
 *     (storedState !== null && state === null) ||
 *     (storedState === null && state !== null);
 *
 * Tests verify every branch of this expression:
 *   A. both null        → match  → login proceeds
 *   B. state null only  → mismatch → error shown
 *   C. stored null only → mismatch → error shown
 *   D. both non-null, different values → mismatch → error shown
 *   E. both non-null, equal values     → match  → login proceeds
 *
 * Fix 3 — cancelled flag prevents acting on stale async result
 * ────────────────────────────────────────────────────────────
 * The component uses a `cancelled` boolean (set in the effect's cleanup)
 * to guard setUser / navigate calls after an unmount.
 *
 * Coverage matrix
 *   CSRF state A: both null → proceeds to login
 *   CSRF state B: state null, storedState non-null → error
 *   CSRF state C: storedState null, state non-null → error
 *   CSRF state D: both non-null, mismatch → error
 *   CSRF state E: both non-null, match → proceeds to login
 *   error param:  access_denied → known message shown
 *   error param:  unknown code → falls back to error_description
 *   error param:  unknown code with no description → generic message
 *   missing code after valid state → error shown
 *   successful login → setUser called + navigate to "/"
 *   login API failure → error message from response.data.detail shown
 *   login API failure → fallback to err.message when no detail
 *   sessionStorage cleared after state match
 *   sessionStorage cleared after state mismatch
 *   loading spinner shown while login is in-flight
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";

// ── Hoisted mocks — vi.hoisted() runs before module evaluation so the fns are
//    available when vi.mock() factories are executed (which are themselves
//    hoisted to the top of the file by Vitest's transformer).
// ─────────────────────────────────────────────────────────────────────────────
const { mockGoogleLogin, mockSetUser, mockNavigate } = vi.hoisted(() => ({
  mockGoogleLogin: vi.fn(),
  mockSetUser: vi.fn(),
  mockNavigate: vi.fn(),
}));

// searchParams must be mutable across tests — keep it module-level but
// re-assign in beforeEach.
let mockSearchParams = new URLSearchParams();

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test-client-id",
  GOOGLE_REDIRECT_URI: "https://marketplace.megdev.com.br/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

vi.mock("@/api/axios", () => ({
  default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
}));

vi.mock("@/services/socialAuthService", () => ({
  socialAuthService: {
    googleLogin: mockGoogleLogin,
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ setUser: mockSetUser }),
}));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [mockSearchParams],
  useNavigate: () => mockNavigate,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

// ── Import component under test (after mocks) ─────────────────────────────────

import { GoogleCallback } from "../index";

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build URLSearchParams for a standard successful callback.
 */
function buildSuccessParams(state: string): URLSearchParams {
  const p = new URLSearchParams();
  p.set("code", "auth-code-123");
  p.set("state", state);
  return p;
}

function renderCallback() {
  return render(<GoogleCallback />);
}

// ─────────────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Reset sessionStorage between tests
  sessionStorage.clear();
  // Reset search params
  mockSearchParams = new URLSearchParams();
});

afterEach(() => {
  sessionStorage.clear();
});

// ─── error query param handling ───────────────────────────────────────────────

describe("GoogleCallback — error query parameter", () => {
  it("shows the Portuguese message for access_denied", () => {
    mockSearchParams.set("error", "access_denied");

    renderCallback();

    expect(
      screen.getByText("Você cancelou a autorização do Google."),
    ).toBeInTheDocument();
  });

  it("shows the Portuguese message for server_error", () => {
    mockSearchParams.set("error", "server_error");

    renderCallback();

    expect(
      screen.getByText("Erro no servidor do Google. Tente novamente."),
    ).toBeInTheDocument();
  });

  it("falls back to error_description for an unknown error code", () => {
    mockSearchParams.set("error", "some_unknown_error");
    mockSearchParams.set("error_description", "Something went wrong.");

    renderCallback();

    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("shows the generic message when error code is unknown and no description", () => {
    mockSearchParams.set("error", "completely_unknown");

    renderCallback();

    expect(
      screen.getByText("Erro na autenticação com Google."),
    ).toBeInTheDocument();
  });

  it("does NOT call googleLogin when an error param is present", () => {
    mockSearchParams.set("error", "access_denied");

    renderCallback();

    expect(mockGoogleLogin).not.toHaveBeenCalled();
  });

  it("shows the error UI heading", () => {
    mockSearchParams.set("error", "access_denied");

    renderCallback();

    expect(screen.getByText("Erro na autenticação")).toBeInTheDocument();
  });

  it("renders a back-to-login button when showing error", () => {
    mockSearchParams.set("error", "access_denied");

    renderCallback();

    expect(
      screen.getByRole("button", { name: /voltar para o login/i }),
    ).toBeInTheDocument();
  });
});

// ─── CSRF state validation ────────────────────────────────────────────────────

describe("GoogleCallback — CSRF state validation (Fix 2)", () => {
  //
  // Case A: both state and storedState are null.
  // state !== storedState → null !== null → false  → no mismatch
  // Proceeds to login (code required).
  //
  it("Case A: both state and storedState null — proceeds (no error shown)", async () => {
    // No state in URL, nothing in sessionStorage
    mockSearchParams.set("code", "auth-code-123");
    // state param absent → searchParams.get("state") === null
    // sessionStorage.getItem("oauth_state") === null

    mockGoogleLogin.mockResolvedValueOnce({
      user: { id: 1, email: "user@test.com", full_name: "User" },
    });

    renderCallback();

    await waitFor(() => {
      expect(mockGoogleLogin).toHaveBeenCalled();
    });
    // No security error rendered
    expect(
      screen.queryByText("Falha na validação de segurança. Tente novamente."),
    ).not.toBeInTheDocument();
  });

  //
  // Case B: state is null (not in URL), storedState is non-null.
  // (storedState !== null && state === null) → true → mismatch
  //
  it("Case B: state absent from URL, storedState present — shows security error", async () => {
    sessionStorage.setItem("oauth_state", "stored-state-abc");
    // No state param in URL → searchParams.get("state") === null
    mockSearchParams.set("code", "auth-code-123");

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Falha na validação de segurança. Tente novamente."),
      ).toBeInTheDocument();
    });
    expect(mockGoogleLogin).not.toHaveBeenCalled();
  });

  //
  // Case C: state is non-null (present in URL), storedState is null (cleared/different session).
  // (storedState === null && state !== null) → true → mismatch
  //
  it("Case C: state present in URL, storedState absent — shows security error", async () => {
    // Nothing in sessionStorage
    mockSearchParams.set("code", "auth-code-123");
    mockSearchParams.set("state", "url-state-xyz");

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Falha na validação de segurança. Tente novamente."),
      ).toBeInTheDocument();
    });
    expect(mockGoogleLogin).not.toHaveBeenCalled();
  });

  //
  // Case D: both non-null but different values — classic CSRF mismatch.
  // state !== storedState → true → mismatch
  //
  it("Case D: state and storedState both present but different — shows security error", async () => {
    sessionStorage.setItem("oauth_state", "legitimate-state");
    mockSearchParams.set("code", "auth-code-123");
    mockSearchParams.set("state", "attacker-injected-state");

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Falha na validação de segurança. Tente novamente."),
      ).toBeInTheDocument();
    });
    expect(mockGoogleLogin).not.toHaveBeenCalled();
  });

  //
  // Case E: both non-null and equal — valid flow.
  // state !== storedState → false, neither subcondition → no mismatch
  //
  it("Case E: state and storedState present and equal — proceeds to login", async () => {
    const state = "matching-state-value";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    mockGoogleLogin.mockResolvedValueOnce({
      user: { id: 1, email: "user@test.com", full_name: "User" },
    });

    renderCallback();

    await waitFor(() => {
      expect(mockGoogleLogin).toHaveBeenCalled();
    });
    expect(
      screen.queryByText("Falha na validação de segurança. Tente novamente."),
    ).not.toBeInTheDocument();
  });

  it("clears sessionStorage after a successful state match", async () => {
    const state = "matching-state-value";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    mockGoogleLogin.mockResolvedValueOnce({
      user: { id: 1, email: "user@test.com", full_name: "User" },
    });

    renderCallback();

    await waitFor(() => expect(mockGoogleLogin).toHaveBeenCalled());

    expect(sessionStorage.getItem("oauth_state")).toBeNull();
  });

  it("clears sessionStorage after a state mismatch to prevent reuse", async () => {
    sessionStorage.setItem("oauth_state", "state-A");
    mockSearchParams.set("code", "code");
    mockSearchParams.set("state", "state-B");

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Falha na validação de segurança. Tente novamente."),
      ).toBeInTheDocument();
    });
    expect(sessionStorage.getItem("oauth_state")).toBeNull();
  });
});

// ─── missing code ─────────────────────────────────────────────────────────────

describe("GoogleCallback — missing code param", () => {
  it("shows an error when code is absent after valid state", async () => {
    // Both null (case A) — no state → no mismatch — but code is missing
    // No state param, no stored state → passes state check, fails code check
    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Código de autenticação não encontrado."),
      ).toBeInTheDocument();
    });
    expect(mockGoogleLogin).not.toHaveBeenCalled();
  });

  it("shows an error when code is absent with matching state", async () => {
    const state = "some-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams.set("state", state);
    // No "code" param

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Código de autenticação não encontrado."),
      ).toBeInTheDocument();
    });
  });
});

// ─── successful login ─────────────────────────────────────────────────────────

describe("GoogleCallback — successful login flow", () => {
  it("calls googleLogin with the code from URL and the configured redirect_uri", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    mockGoogleLogin.mockResolvedValueOnce({
      user: { id: 99, email: "test@gmail.com", full_name: "Test User" },
    });

    renderCallback();

    await waitFor(() => expect(mockGoogleLogin).toHaveBeenCalled());

    expect(mockGoogleLogin).toHaveBeenCalledWith({
      code: "auth-code-123",
      redirect_uri: "https://marketplace.megdev.com.br/auth/google/callback",
    });
  });

  it("calls setUser with the user returned by googleLogin", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    const user = { id: 99, email: "test@gmail.com", full_name: "Test User" };
    mockGoogleLogin.mockResolvedValueOnce({ user });

    renderCallback();

    await waitFor(() => expect(mockSetUser).toHaveBeenCalledWith(user));
  });

  it("navigates to '/' with replace:true after successful login", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    mockGoogleLogin.mockResolvedValueOnce({
      user: { id: 1, email: "u@test.com", full_name: "U" },
    });

    renderCallback();

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true }),
    );
  });

  it("shows the loading spinner while login is in flight", () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    // Never resolves — keeps component in loading state
    mockGoogleLogin.mockImplementation(() => new Promise(() => {}));

    renderCallback();

    expect(screen.getByText("Autenticando com Google...")).toBeInTheDocument();
  });
});

// ─── login API failure ────────────────────────────────────────────────────────

describe("GoogleCallback — login API failure", () => {
  it("shows response.data.detail when the API returns a structured error", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    const error = Object.assign(new Error("Unauthorized"), {
      isAxiosError: true,
      response: { status: 401, data: { detail: "Invalid authorisation code." } },
    });
    mockGoogleLogin.mockRejectedValueOnce(error);

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Invalid authorisation code."),
      ).toBeInTheDocument();
    });
  });

  it("falls back to err.message when response has no detail field", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    const error = Object.assign(new Error("Network Error"), {
      isAxiosError: true,
      response: { status: 503, data: {} },
    });
    mockGoogleLogin.mockRejectedValueOnce(error);

    renderCallback();

    await waitFor(() => {
      expect(screen.getByText("Network Error")).toBeInTheDocument();
    });
  });

  it("shows the generic fallback when error has no response and no message", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    // Simulates an error object with no message and no response
    const error = Object.create(null);
    mockGoogleLogin.mockRejectedValueOnce(error);

    renderCallback();

    await waitFor(() => {
      expect(
        screen.getByText("Erro ao autenticar com Google. Tente novamente."),
      ).toBeInTheDocument();
    });
  });

  it("does NOT call setUser or navigate when the login API call fails", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    mockGoogleLogin.mockRejectedValueOnce(
      Object.assign(new Error("Fail"), { response: { data: { detail: "Fail" } } }),
    );

    renderCallback();

    await waitFor(() => screen.getByText("Fail"));

    expect(mockSetUser).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalledWith("/", expect.anything());
  });
});

// ─── double-invocation prevention (Fix 3) ────────────────────────────────────

describe("GoogleCallback — effect cleanup / cancellation (Fix 3)", () => {
  it("does not call setUser or navigate when the component unmounts before googleLogin resolves", async () => {
    const state = "valid-state";
    sessionStorage.setItem("oauth_state", state);
    mockSearchParams = buildSuccessParams(state);

    let resolveLogin!: (v: unknown) => void;
    mockGoogleLogin.mockImplementation(
      () => new Promise((res) => { resolveLogin = res; }),
    );

    const { unmount } = renderCallback();

    // Unmount before the promise resolves — simulates StrictMode double-mount
    // or navigation away from the page during the async exchange.
    unmount();

    // Now resolve the promise — the cancelled flag should prevent side effects.
    resolveLogin({ user: { id: 1, email: "u@test.com", full_name: "U" } });

    // Give microtasks a chance to run
    await Promise.resolve();

    expect(mockSetUser).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalledWith("/", expect.anything());
  });
});
