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
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from "@/api/axios";
import { listingImageService } from "../listingImageService";

const mockApi = api as unknown as {
  post: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listingImageService.addImage", () => {
  it("posts to the correct endpoint with payload", async () => {
    const apiResponse = {
      image_url: "http://localhost:9000/bucket/img.jpg",
      object_name: "listings/42/img.jpg",
      is_primary: true,
      order: 0,
    };
    mockApi.post.mockResolvedValueOnce({ data: apiResponse });

    const result = await listingImageService.addImage(42, {
      image_url: "http://localhost:9000/bucket/img.jpg",
      object_name: "listings/42/img.jpg",
      is_primary: true,
      order: 0,
    });

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/listings/42/images/",
      {
        image_url: "http://localhost:9000/bucket/img.jpg",
        object_name: "listings/42/img.jpg",
        is_primary: true,
        order: 0,
      },
    );
    expect(result.image_url).toBe("http://localhost:9000/bucket/img.jpg");
    expect(result.object_name).toBe("listings/42/img.jpg");
  });

  it("sends is_primary as false when not primary", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: {
        image_url: "http://localhost:9000/bucket/img.jpg",
        object_name: "listings/42/img.jpg",
        is_primary: false,
        order: 1,
      },
    });

    await listingImageService.addImage(42, {
      image_url: "http://localhost:9000/bucket/img.jpg",
      object_name: "listings/42/img.jpg",
      is_primary: false,
      order: 1,
    });

    const calledWith = mockApi.post.mock.calls[0][1];
    expect(calledWith.is_primary).toBe(false);
  });

  it("propagates 400 validation error", async () => {
    const error = Object.assign(new Error("Bad Request"), {
      isAxiosError: true,
      response: {
        status: 400,
        data: { image_url: ["This field is required."] },
      },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(
      listingImageService.addImage(42, {
        image_url: "",
        object_name: "obj",
        is_primary: false,
        order: 0,
      }),
    ).rejects.toThrow("Bad Request");
  });

  it("propagates 403 when user does not own listing", async () => {
    const error = Object.assign(new Error("Forbidden"), {
      isAxiosError: true,
      response: { status: 403, data: { detail: "Permission denied." } },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(
      listingImageService.addImage(99, {
        image_url: "http://localhost:9000/bucket/img.jpg",
        object_name: "obj",
        is_primary: false,
        order: 0,
      }),
    ).rejects.toThrow("Forbidden");
  });

  it("create response does NOT include id (documents API contract)", async () => {
    const apiResponse = {
      image_url: "http://localhost:9000/bucket/img.jpg",
      object_name: "listings/42/img.jpg",
      is_primary: true,
      order: 0,
      // Intentionally no id or created_at — this is what the API really returns
    };
    mockApi.post.mockResolvedValueOnce({ data: apiResponse });

    const result = await listingImageService.addImage(42, {
      image_url: "http://localhost:9000/bucket/img.jpg",
      object_name: "listings/42/img.jpg",
      is_primary: true,
      order: 0,
    });

    expect(result).not.toHaveProperty("id");
    expect(result).not.toHaveProperty("created_at");
  });
});

describe("listingImageService.setPrimary", () => {
  it("posts to the correct set-primary endpoint", async () => {
    mockApi.post.mockResolvedValueOnce({
      data: { message: "Primary image set." },
    });

    const result = await listingImageService.setPrimary(42, 7);

    expect(mockApi.post).toHaveBeenCalledWith(
      "/products/listings/42/images/7/set-primary/",
    );
    expect(result.message).toBe("Primary image set.");
  });

  it("propagates 404 when image does not exist", async () => {
    const error = Object.assign(new Error("Not Found"), {
      isAxiosError: true,
      response: { status: 404 },
    });
    mockApi.post.mockRejectedValueOnce(error);

    await expect(listingImageService.setPrimary(42, 9999)).rejects.toThrow(
      "Not Found",
    );
  });
});

describe("listingImageService.deleteImage", () => {
  it("calls delete on the correct endpoint", async () => {
    mockApi.delete.mockResolvedValueOnce({ data: undefined });

    await listingImageService.deleteImage(42, 7);

    expect(mockApi.delete).toHaveBeenCalledWith(
      "/products/listings/42/images/7/delete/",
    );
  });

  it("resolves with undefined (204 no body)", async () => {
    mockApi.delete.mockResolvedValueOnce({ data: undefined });

    const result = await listingImageService.deleteImage(42, 7);
    expect(result).toBeUndefined();
  });

  it("propagates 404 when image already deleted", async () => {
    const error = Object.assign(new Error("Not Found"), {
      isAxiosError: true,
      response: { status: 404 },
    });
    mockApi.delete.mockRejectedValueOnce(error);

    await expect(listingImageService.deleteImage(42, 7)).rejects.toThrow(
      "Not Found",
    );
  });
});
