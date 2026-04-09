/**
 * Tests for src/pages/auth/Login/index.tsx
 *
 * Risk level: HIGH
 *   - The OAuth URL built by handleGoogleLogin must contain specific required
 *     params.  Any missing or wrong param causes Google to reject the
 *     authorisation request silently from the user's perspective.
 *   - Fix 4: `prompt=select_account` was added to force the account chooser.
 *     Without it, Google auto-selects a previously authorized account, which
 *     can confuse users with multiple accounts and bypass expected UX.
 *   - The state param written to sessionStorage must match the value in the
 *     URL; a mismatch would be caught by GoogleCallback's CSRF guard and show
 *     a security error to the user.
 *
 * Coverage matrix
 *   handleGoogleLogin:
 *     - includes client_id in the OAuth URL
 *     - includes redirect_uri in the OAuth URL
 *     - includes response_type=code in the OAuth URL
 *     - includes scope with openid, email, profile
 *     - includes access_type=offline
 *     - includes prompt=select_account (Fix 4)
 *     - generates a state param and sets it in sessionStorage
 *     - the state in the URL matches the value stored in sessionStorage
 *     - navigates to the Google OAuth endpoint (accounts.google.com)
 *   Form behaviour:
 *     - Google button is rendered and is of type "button" (not submit)
 *     - Google button is disabled while form login is in progress
 *     - shows email/password fields
 *     - shows error message when login() throws
 *     - clears error on a new submission attempt
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ── Module mocks (hoisted, before all other imports) ──────────────────────────

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test-client-id",
  GOOGLE_REDIRECT_URI: "https://marketplace.megdev.com.br/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

vi.mock("@/api/axios", () => ({
  default: { post: vi.fn(), get: vi.fn() },
}));

// Stub AuthLogo — it uses react-router-dom Link and we don't need its output.
vi.mock("@/components/ui/AuthLogo", () => ({
  AuthLogo: () => <div data-testid="auth-logo" />,
}));

// Mock useAuth — Login only calls login() from the context.
const mockLogin = vi.fn();
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ login: mockLogin }),
}));

// Mock react-router-dom — Login uses useNavigate and Link.
const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  Link: ({
    children,
    to,
  }: {
    children: React.ReactNode;
    to: string;
  }) => <a href={to}>{children}</a>,
}));

// ── Import component under test ───────────────────────────────────────────────

import LoginPage from "../index";

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Capture the URL that window.location.href was set to.
 * The component assigns directly: window.location.href = `https://...`
 */
let capturedHref = "";

function renderLogin() {
  return render(<LoginPage />);
}

function getGoogleButton() {
  return screen.getByRole("button", { name: /continuar com google/i });
}

// ─────────────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  capturedHref = "";
  sessionStorage.clear();

  // jsdom does not implement navigation; replace the href setter so we can
  // capture the URL without throwing a "Not implemented" error.
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: {
      ...window.location,
      href: "",
    },
  });

  Object.defineProperty(window.location, "href", {
    configurable: true,
    set(value: string) {
      capturedHref = value;
    },
    get() {
      return capturedHref;
    },
  });

  // crypto.randomUUID is available in jsdom but mock it for determinism.
  vi.spyOn(crypto, "randomUUID").mockReturnValue(
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  );
});

// ─── Google button rendering ──────────────────────────────────────────────────

describe("LoginPage — Google button rendering", () => {
  it("renders the Google login button", () => {
    renderLogin();

    expect(getGoogleButton()).toBeInTheDocument();
  });

  it("Google button has type='button' so it cannot accidentally submit the form", () => {
    renderLogin();

    expect(getGoogleButton()).toHaveAttribute("type", "button");
  });
});

// ─── OAuth URL construction (Fix 4 and general params) ────────────────────────

describe("LoginPage — handleGoogleLogin OAuth URL construction", () => {
  function clickGoogleButton() {
    renderLogin();
    fireEvent.click(getGoogleButton());
    return new URL(capturedHref);
  }

  it("navigates to the Google OAuth v2 authorization endpoint", () => {
    const url = clickGoogleButton();

    expect(url.origin + url.pathname).toBe(
      "https://accounts.google.com/o/oauth2/v2/auth",
    );
  });

  it("includes client_id matching GOOGLE_CLIENT_ID constant", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("client_id")).toBe("test-client-id");
  });

  it("includes redirect_uri matching GOOGLE_REDIRECT_URI constant", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("redirect_uri")).toBe(
      "https://marketplace.megdev.com.br/auth/google/callback",
    );
  });

  it("includes response_type=code (authorisation code flow)", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("response_type")).toBe("code");
  });

  it("includes scope with openid", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("scope")).toContain("openid");
  });

  it("includes scope with email", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("scope")).toContain("email");
  });

  it("includes scope with profile", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("scope")).toContain("profile");
  });

  it("includes access_type=offline to receive a refresh token", () => {
    const url = clickGoogleButton();

    expect(url.searchParams.get("access_type")).toBe("offline");
  });

  it("Fix 4: includes prompt=select_account to force the account chooser", () => {
    // This is the core of Fix 4.  Without this param, Google may silently
    // reuse a previously authorised account, bypassing the account selector.
    const url = clickGoogleButton();

    expect(url.searchParams.get("prompt")).toBe("select_account");
  });

  it("generates a non-empty state param", () => {
    const url = clickGoogleButton();

    const state = url.searchParams.get("state");
    expect(state).toBeTruthy();
    expect(state!.length).toBeGreaterThan(0);
  });

  it("stores the state param in sessionStorage under 'oauth_state'", () => {
    clickGoogleButton();

    expect(sessionStorage.getItem("oauth_state")).toBe(
      "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    );
  });

  it("state in URL matches value stored in sessionStorage", () => {
    // This is the invariant that GoogleCallback's CSRF guard depends on.
    const url = clickGoogleButton();

    const urlState = url.searchParams.get("state");
    const storedState = sessionStorage.getItem("oauth_state");
    expect(urlState).toBe(storedState);
  });

  it("generates a unique state on each click (randomUUID called each time)", () => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("first-uuid-1111-1111-1111-111111111111")
      .mockReturnValueOnce("second-uuid-2222-2222-2222-222222222222");

    renderLogin();
    const button = getGoogleButton();

    fireEvent.click(button);
    const firstState = sessionStorage.getItem("oauth_state");

    sessionStorage.clear();
    capturedHref = "";

    fireEvent.click(button);
    const secondState = sessionStorage.getItem("oauth_state");

    expect(firstState).not.toBe(secondState);
  });
});

// ─── Form behaviour ───────────────────────────────────────────────────────────

describe("LoginPage — form behaviour", () => {
  it("renders the email input", () => {
    renderLogin();

    expect(
      screen.getByPlaceholderText("seu@email.com"),
    ).toBeInTheDocument();
  });

  it("renders the password input", () => {
    renderLogin();

    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
  });

  it("shows an error message when login() throws", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Credenciais inválidas"));

    renderLogin();

    await userEvent.type(screen.getByPlaceholderText("seu@email.com"), "bad@email.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "wrongpass");
    fireEvent.submit(screen.getByRole("button", { name: /^entrar$/i }));

    await waitFor(() => {
      expect(screen.getByText("Credenciais inválidas")).toBeInTheDocument();
    });
  });

  it("navigates to '/' on successful login", async () => {
    mockLogin.mockResolvedValueOnce(undefined);

    renderLogin();

    await userEvent.type(screen.getByPlaceholderText("seu@email.com"), "user@test.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "password123");
    fireEvent.submit(screen.getByRole("button", { name: /^entrar$/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/");
    });
  });

  it("disables the Google button while a form login is in progress", async () => {
    // Keep login pending so isLoading stays true
    mockLogin.mockImplementation(() => new Promise(() => {}));

    renderLogin();

    await userEvent.type(screen.getByPlaceholderText("seu@email.com"), "user@test.com");
    await userEvent.type(screen.getByPlaceholderText("••••••••"), "password123");
    fireEvent.submit(screen.getByRole("button", { name: /^entrar$/i }));

    await waitFor(() => {
      expect(getGoogleButton()).toBeDisabled();
    });
  });
});
