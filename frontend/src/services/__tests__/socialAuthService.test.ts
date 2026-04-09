/**
 * Tests for src/services/socialAuthService.ts
 *
 * Risk level: HIGH
 *   - googleLogin() is the OAuth exchange endpoint.  Any mistake in the POST
 *     body, token-storage call, or user-mapping silently breaks authentication
 *     for all Google-login users.
 *   - The /auth/social/ exclusion in the axios interceptor means 401 errors
 *     from this endpoint propagate directly.  The service must therefore not
 *     swallow them and must forward the full API response.
 *   - googleConnect() must send redirect_uri so the backend can validate the
 *     callback URL.  Omitting it causes a backend rejection.
 *
 * Coverage matrix
 *   googleLogin  : posts correct endpoint + body (code, redirect_uri),
 *                  maps pk → id + constructs full_name from first/last name,
 *                  maps full_name when only first_name present,
 *                  maps full_name when only last_name present,
 *                  maps full_name to empty string when both name parts absent,
 *                  saves tokens via tokenStorage.saveTokens,
 *                  saves user via tokenStorage.saveUser,
 *                  returns tokens + mapped user,
 *                  propagates 401 errors (no swallowing)
 *   googleConnect: posts to the correct connect endpoint,
 *                  sends redirect_uri in body,
 *                  returns the API response verbatim,
 *                  propagates 400 errors
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Constants mock must be hoisted above all imports that transitively need it.
vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test-client-id",
  GOOGLE_REDIRECT_URI: "https://marketplace.megdev.com.br/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

vi.mock("@/api/axios", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

// tokenStorage is used by googleLogin to persist tokens/user — spy on it
// so we can assert the correct values are stored without touching localStorage.
vi.mock("@/utils/tokenStorage", () => ({
  tokenStorage: {
    saveTokens: vi.fn(),
    saveUser: vi.fn(),
    getAccessToken: vi.fn(),
    getRefreshToken: vi.fn(),
    clearTokens: vi.fn(),
    isRefreshTokenExpired: vi.fn(),
  },
}));

import api from "@/api/axios";
import { tokenStorage } from "@/utils/tokenStorage";
import { socialAuthService } from "../socialAuthService";

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

const mockTokenStorage = tokenStorage as unknown as {
  saveTokens: ReturnType<typeof vi.fn>;
  saveUser: ReturnType<typeof vi.fn>;
};

// ── Fixtures ──────────────────────────────────────────────────────────────────

const API_RESPONSE = {
  access: "access-token-abc",
  refresh: "refresh-token-xyz",
  access_expiration: "2026-02-28T12:00:00Z",
  refresh_expiration: "2026-03-07T12:00:00Z",
  user: {
    pk: 42,
    username: "joaosilva",
    email: "joao@example.com",
    first_name: "João",
    last_name: "Silva",
  },
};

const REDIRECT_URI = "https://marketplace.megdev.com.br/auth/google/callback";

// ─────────────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── googleLogin ──────────────────────────────────────────────────────────────

describe("socialAuthService.googleLogin", () => {
  it("posts to /auth/social/google/ with code and redirect_uri", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(mockApi.post).toHaveBeenCalledWith("/auth/social/google/", {
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });
  });

  it("maps api user.pk to user.id", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    const result = await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.id).toBe(42);
  });

  it("maps api user.email verbatim", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    const result = await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.email).toBe("joao@example.com");
  });

  it("constructs full_name by joining first_name and last_name", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    const result = await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.full_name).toBe("João Silva");
  });

  it("builds full_name from first_name only when last_name is empty", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        ...API_RESPONSE,
        user: { ...API_RESPONSE.user, last_name: "" },
      },
    });

    const result = await socialAuthService.googleLogin({
      code: "code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.full_name).toBe("João");
  });

  it("builds full_name from last_name only when first_name is empty", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        ...API_RESPONSE,
        user: { ...API_RESPONSE.user, first_name: "" },
      },
    });

    const result = await socialAuthService.googleLogin({
      code: "code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.full_name).toBe("Silva");
  });

  it("sets full_name to empty string when both first_name and last_name are empty", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        ...API_RESPONSE,
        user: { ...API_RESPONSE.user, first_name: "", last_name: "" },
      },
    });

    const result = await socialAuthService.googleLogin({
      code: "code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.full_name).toBe("");
  });

  it("sets static default fields: birthday, cpf, picture as empty string, is_active as true", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    const result = await socialAuthService.googleLogin({
      code: "code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.user.birthday).toBe("");
    expect(result.user.cpf).toBe("");
    expect(result.user.picture).toBe("");
    expect(result.user.is_active).toBe(true);
  });

  it("calls tokenStorage.saveTokens with all four token fields", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(mockTokenStorage.saveTokens).toHaveBeenCalledOnce();
    expect(mockTokenStorage.saveTokens).toHaveBeenCalledWith({
      access: "access-token-abc",
      refresh: "refresh-token-xyz",
      access_expiration: "2026-02-28T12:00:00Z",
      refresh_expiration: "2026-03-07T12:00:00Z",
    });
  });

  it("calls tokenStorage.saveUser with the mapped user object", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    await socialAuthService.googleLogin({
      code: "auth-code-123",
      redirect_uri: REDIRECT_URI,
    });

    expect(mockTokenStorage.saveUser).toHaveBeenCalledOnce();
    const savedUser = mockTokenStorage.saveUser.mock.calls[0][0];
    expect(savedUser.id).toBe(42);
    expect(savedUser.email).toBe("joao@example.com");
    expect(savedUser.full_name).toBe("João Silva");
  });

  it("returns access and refresh tokens from the API response", async () => {
    mockApi.post.mockResolvedValueOnce({ data: API_RESPONSE });

    const result = await socialAuthService.googleLogin({
      code: "code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.access).toBe("access-token-abc");
    expect(result.refresh).toBe("refresh-token-xyz");
    expect(result.access_expiration).toBe("2026-02-28T12:00:00Z");
    expect(result.refresh_expiration).toBe("2026-03-07T12:00:00Z");
  });

  it("propagates 401 error without swallowing it", async () => {
    // This verifies that the service does NOT catch 401s internally.
    // The axios interceptor already excludes /auth/social/ from the refresh
    // logic, so a 401 here means the backend actively rejected the code.
    // The service must surface that error to the caller (GoogleCallback).
    const error = Object.assign(new Error("Unauthorized"), {
      isAxiosError: true,
      response: {
        status: 401,
        data: { detail: "Invalid code." },
      },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(
      socialAuthService.googleLogin({ code: "bad-code", redirect_uri: REDIRECT_URI }),
    ).rejects.toThrow("Unauthorized");
  });

  it("propagates network errors to the caller", async () => {
    mockApi.post.mockRejectedValueOnce(new Error("Network Error"));

    await expect(
      socialAuthService.googleLogin({ code: "code", redirect_uri: REDIRECT_URI }),
    ).rejects.toThrow("Network Error");
  });

  it("does NOT call tokenStorage when the API request fails", async () => {
    mockApi.post.mockRejectedValueOnce(new Error("Server Error"));

    await socialAuthService
      .googleLogin({ code: "code", redirect_uri: REDIRECT_URI })
      .catch(() => {});

    expect(mockTokenStorage.saveTokens).not.toHaveBeenCalled();
    expect(mockTokenStorage.saveUser).not.toHaveBeenCalled();
  });
});

// ─── googleConnect ────────────────────────────────────────────────────────────

describe("socialAuthService.googleConnect", () => {
  it("posts to /auth/social/google/connect/", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        message: "Account connected.",
        account: { id: 1, provider: "google", uid: "uid-abc", extra_data: {}, date_joined: "2026-01-01" },
      },
    });

    await socialAuthService.googleConnect({
      code: "connect-code",
      redirect_uri: REDIRECT_URI,
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/auth/social/google/connect/",
      expect.objectContaining({ code: "connect-code" }),
    );
  });

  it("sends redirect_uri in the POST body", async () => {
    // Fix 1 context: the backend validates redirect_uri to prevent
    // authorisation-code interception attacks.  Omitting it would cause a
    // backend rejection; this test guarantees it is always forwarded.
    mockApi.post.mockResolvedValueOnce({
      data: {
        message: "Account connected.",
        account: { id: 1, provider: "google", uid: "uid-abc", extra_data: {}, date_joined: "2026-01-01" },
      },
    });

    await socialAuthService.googleConnect({
      code: "connect-code",
      redirect_uri: REDIRECT_URI,
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/auth/social/google/connect/",
      expect.objectContaining({ redirect_uri: REDIRECT_URI }),
    );
  });

  it("returns the API response with message and account fields", async () => {
    const apiPayload = {
      message: "Account connected.",
      account: {
        id: 7,
        provider: "google",
        uid: "google-uid-xyz",
        extra_data: { email: "user@gmail.com" },
        date_joined: "2026-01-15T10:00:00Z",
      },
    };
    mockApi.post.mockResolvedValueOnce({ data: apiPayload });

    const result = await socialAuthService.googleConnect({
      code: "connect-code",
      redirect_uri: REDIRECT_URI,
    });

    expect(result.message).toBe("Account connected.");
    expect(result.account.id).toBe(7);
    expect(result.account.provider).toBe("google");
  });

  it("works when redirect_uri is omitted (optional field)", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        message: "ok",
        account: { id: 1, provider: "google", uid: "u", extra_data: {}, date_joined: "2026-01-01" },
      },
    });

    await expect(
      socialAuthService.googleConnect({ code: "code" }),
    ).resolves.toBeDefined();

    expect(mockApi.post).toHaveBeenCalledWith(
      "/auth/social/google/connect/",
      { code: "code" },
    );
  });

  it("propagates 400 validation error from the API", async () => {
    const error = Object.assign(new Error("Bad Request"), {
      isAxiosError: true,
      response: { status: 400, data: { code: ["Invalid code."] } },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(
      socialAuthService.googleConnect({ code: "bad", redirect_uri: REDIRECT_URI }),
    ).rejects.toThrow("Bad Request");
  });
});
