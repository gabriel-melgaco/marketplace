/**
 * Tests for src/services/logisticsService.ts
 *
 * Strategy: mock the shared axios instance (`@/api/axios`) to intercept HTTP
 * calls.  Tests assert on (a) the correct endpoint + params being used and
 * (b) the correct transformation of API responses.
 *
 * Risk level: HIGH
 *   - CEP lookup populates address fields automatically; wrong transformation
 *     silently ships to the wrong address.
 *   - Address CRUD errors block listing creation (step 7 → 8 transition).
 *   - getAddresses() handles two response shapes (array vs paginated object);
 *     a regression here breaks the saved-address flow entirely.
 *
 * Coverage matrix
 *   lookupCep            : strips non-digits, correct POST endpoint + body,
 *                          maps response fields, propagates network error
 *   getAddresses         : handles array response, handles paginated object,
 *                          handles empty results
 *   createAddress        : posts correct payload, returns created object
 *   updateAddress        : patches correct endpoint with partial payload
 *   setDefaultAddress    : posts to the set-default endpoint
 *   getMelhorEnvioStatus : delegates to correct endpoint
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test",
  GOOGLE_REDIRECT_URI: "http://localhost:5173/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

vi.mock("@/api/axios", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import api from "@/api/axios";
import { logisticsService } from "../logisticsService";
import type { AddressData, CepLookupResponse } from "../logisticsService";

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const ADDRESS_FIXTURE: AddressData = {
  id: 1,
  address_type: "shipping",
  zipcode: "01310100",
  street: "Avenida Paulista",
  number: "1000",
  complement: "Apto 42",
  neighborhood: "Bela Vista",
  city: "São Paulo",
  state: "SP",
  country: "BR",
  is_default: false,
  is_active: true,
};

const CEP_RESPONSE_FIXTURE: CepLookupResponse = {
  zipcode: "01310-100",
  street: "Avenida Paulista",
  complement: "",
  neighborhood: "Bela Vista",
  city: "São Paulo",
  state: "SP",
};

// ─── lookupCep ────────────────────────────────────────────────────────────────

describe("logisticsService.lookupCep", () => {
  it("posts to the correct endpoint with zipcode in the body (formatted CEP)", async () => {
    mockApi.post.mockResolvedValueOnce({ data: CEP_RESPONSE_FIXTURE });

    await logisticsService.lookupCep("01310-100");

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/cep/lookup/",
      { zipcode: "01310100" },
    );
  });

  it("strips all non-digit characters from the CEP before posting", async () => {
    mockApi.post.mockResolvedValueOnce({ data: CEP_RESPONSE_FIXTURE });

    await logisticsService.lookupCep("01.310-100");

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/cep/lookup/",
      { zipcode: "01310100" },
    );
  });

  it("accepts a CEP already without formatting characters", async () => {
    mockApi.post.mockResolvedValueOnce({ data: CEP_RESPONSE_FIXTURE });

    await logisticsService.lookupCep("01310100");

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/cep/lookup/",
      { zipcode: "01310100" },
    );
  });

  it("returns the full API response with correct field names", async () => {
    mockApi.post.mockResolvedValueOnce({ data: CEP_RESPONSE_FIXTURE });

    const result = await logisticsService.lookupCep("01310100");

    expect(result.street).toBe("Avenida Paulista");
    expect(result.neighborhood).toBe("Bela Vista");
    expect(result.city).toBe("São Paulo");
    expect(result.state).toBe("SP");
  });

  it("propagates network errors to the caller", async () => {
    const networkError = new Error("Network Error");
    mockApi.post.mockRejectedValueOnce(networkError);

    await expect(logisticsService.lookupCep("01310100")).rejects.toThrow(
      "Network Error",
    );
  });
});

// ─── getAddresses ─────────────────────────────────────────────────────────────

describe("logisticsService.getAddresses", () => {
  it("returns array directly when API responds with a plain array", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [ADDRESS_FIXTURE] });

    const result = await logisticsService.getAddresses();

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(1);
  });

  it("extracts results when API responds with paginated object", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [ADDRESS_FIXTURE] },
    });

    const result = await logisticsService.getAddresses();

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(1);
  });

  it("returns empty array when paginated results is empty", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: { count: 0, next: null, previous: null, results: [] },
    });

    const result = await logisticsService.getAddresses();

    expect(result).toEqual([]);
  });

  it("returns empty array when plain array response is empty", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });

    const result = await logisticsService.getAddresses();

    expect(result).toEqual([]);
  });

  it("calls the correct endpoint", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });

    await logisticsService.getAddresses();

    expect(mockApi.get).toHaveBeenCalledWith("/logistics/addresses/");
  });
});

// ─── createAddress ────────────────────────────────────────────────────────────

describe("logisticsService.createAddress", () => {
  it("posts to the correct endpoint", async () => {
    mockApi.post.mockResolvedValueOnce({ data: ADDRESS_FIXTURE });

    await logisticsService.createAddress({
      zipcode: "01310100",
      street: "Avenida Paulista",
      number: "1000",
      neighborhood: "Bela Vista",
      city: "São Paulo",
      state: "SP",
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/addresses/",
      expect.objectContaining({
        zipcode: "01310100",
        street: "Avenida Paulista",
      }),
    );
  });

  it("returns the created address object from the API", async () => {
    mockApi.post.mockResolvedValueOnce({ data: ADDRESS_FIXTURE });

    const result = await logisticsService.createAddress({
      zipcode: "01310100",
      street: "Avenida Paulista",
      number: "1000",
      neighborhood: "Bela Vista",
      city: "São Paulo",
      state: "SP",
    });

    expect(result.id).toBe(1);
    expect(result.city).toBe("São Paulo");
  });

  it("propagates 400 validation error from the API", async () => {
    const error = Object.assign(new Error("Bad Request"), {
      isAxiosError: true,
      response: { status: 400, data: { zipcode: ["Invalid zipcode."] } },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(
      logisticsService.createAddress({
        zipcode: "invalid",
        street: "Rua",
        number: "1",
        neighborhood: "Bairro",
        city: "Cidade",
        state: "SP",
      }),
    ).rejects.toThrow("Bad Request");
  });

  it("sends optional complement field when provided", async () => {
    mockApi.post.mockResolvedValueOnce({ data: ADDRESS_FIXTURE });

    await logisticsService.createAddress({
      zipcode: "01310100",
      street: "Avenida Paulista",
      number: "1000",
      complement: "Sala 5",
      neighborhood: "Bela Vista",
      city: "São Paulo",
      state: "SP",
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/addresses/",
      expect.objectContaining({ complement: "Sala 5" }),
    );
  });
});

// ─── updateAddress ────────────────────────────────────────────────────────────

describe("logisticsService.updateAddress", () => {
  it("patches the correct address endpoint with the partial payload", async () => {
    mockApi.patch.mockResolvedValueOnce({
      data: { ...ADDRESS_FIXTURE, number: "2000" },
    });

    await logisticsService.updateAddress(1, { number: "2000" });

    expect(mockApi.patch).toHaveBeenCalledWith(
      "/logistics/addresses/1/",
      { number: "2000" },
    );
  });

  it("returns the updated address from the API response", async () => {
    const updated = { ...ADDRESS_FIXTURE, number: "2000" };
    mockApi.patch.mockResolvedValueOnce({ data: updated });

    const result = await logisticsService.updateAddress(1, { number: "2000" });

    expect(result.number).toBe("2000");
  });
});

// ─── setDefaultAddress ────────────────────────────────────────────────────────

describe("logisticsService.setDefaultAddress", () => {
  it("posts to the set-default endpoint for the given id", async () => {
    mockApi.post.mockResolvedValueOnce({ data: {} });

    await logisticsService.setDefaultAddress(42);

    expect(mockApi.post).toHaveBeenCalledWith(
      "/logistics/addresses/42/set-default/",
    );
  });

  it("resolves without returning a value (void)", async () => {
    mockApi.post.mockResolvedValueOnce({ data: {} });

    const result = await logisticsService.setDefaultAddress(42);

    expect(result).toBeUndefined();
  });
});

// ─── getMelhorEnvioStatus ─────────────────────────────────────────────────────

describe("logisticsService.getMelhorEnvioStatus", () => {
  it("calls the correct ME status endpoint", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        connected: true,
        environment: "sandbox",
        me_email: "seller@example.com",
        access_token: "token123",
        is_expired: false,
        expires_at: null,
        expires_in_seconds: 3600,
        is_refresh_token_expired: false,
        last_refreshed_at: null,
      },
    });

    const result = await logisticsService.getMelhorEnvioStatus();

    expect(mockApi.get).toHaveBeenCalledWith("/logistics/me/status/");
    expect(result.connected).toBe(true);
    expect(result.is_expired).toBe(false);
  });

  it("returns connected=false when not linked", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        connected: false,
        environment: "production",
        me_email: null,
        access_token: null,
        is_expired: null,
        expires_at: null,
        expires_in_seconds: null,
        is_refresh_token_expired: null,
        last_refreshed_at: null,
      },
    });

    const result = await logisticsService.getMelhorEnvioStatus();

    expect(result.connected).toBe(false);
    expect(result.me_email).toBeNull();
  });
});
