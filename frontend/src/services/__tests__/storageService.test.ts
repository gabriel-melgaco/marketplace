import { describe, it, expect, vi } from "vitest";
import {
  toPublicUrl,
  validateImageFile,
  isRetryableError,
  IMAGE_UPLOAD_LIMITS,
} from "../storageService";

// Mock MINIO_PUBLIC_URL
vi.mock("@/utils/constants", () => ({
  MINIO_PUBLIC_URL: "http://localhost:9000",
}));

// Mock api/axios (not used in these tests but imported by storageService)
vi.mock("@/api/axios", () => ({
  default: { post: vi.fn() },
}));

describe("toPublicUrl", () => {
  it("returns empty string for empty input", () => {
    expect(toPublicUrl("")).toBe("");
  });

  it("returns URL unchanged if already using public host", () => {
    const url = "http://localhost:9000/bucket/file.jpg?X-Amz-Signature=abc";
    expect(toPublicUrl(url)).toBe(url);
  });

  it("replaces internal Docker hostname with public URL", () => {
    const internal = "http://minio:9000/bucket/file.jpg?X-Amz-Signature=abc";
    const result = toPublicUrl(internal);
    expect(result).toContain("localhost:9000");
    expect(result).toContain("/bucket/file.jpg");
    expect(result).toContain("X-Amz-Signature=abc");
  });

  it("preserves query params (presigned URL signatures)", () => {
    const internal =
      "http://minio:9000/bucket/file.jpg?X-Amz-Algorithm=AWS4&X-Amz-Signature=abc123";
    const result = toPublicUrl(internal);
    expect(result).toContain("X-Amz-Algorithm=AWS4");
    expect(result).toContain("X-Amz-Signature=abc123");
  });

  it("preserves path with nested directories", () => {
    const internal = "http://minio:9000/bucket/2024/01/15/image.webp";
    const result = toPublicUrl(internal);
    expect(result).toContain("/bucket/2024/01/15/image.webp");
  });

  it("returns malformed URL unchanged with a warning", () => {
    const consoleSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const badUrl = "not-a-url";
    expect(toPublicUrl(badUrl)).toBe(badUrl);
    expect(consoleSpy).toHaveBeenCalledWith(
      "[StorageService] Failed to parse URL:",
      badUrl,
    );
    consoleSpy.mockRestore();
  });
});

describe("validateImageFile", () => {
  function createMockFile(
    name: string,
    size: number,
    type: string,
  ): File {
    const blob = new Blob(["x".repeat(size)], { type });
    return new File([blob], name, { type });
  }

  it("accepts valid JPEG file", () => {
    const file = createMockFile("photo.jpg", 1024, "image/jpeg");
    expect(() => validateImageFile(file)).not.toThrow();
  });

  it("accepts valid PNG file", () => {
    const file = createMockFile("photo.png", 1024, "image/png");
    expect(() => validateImageFile(file)).not.toThrow();
  });

  it("accepts valid WebP file", () => {
    const file = createMockFile("photo.webp", 1024, "image/webp");
    expect(() => validateImageFile(file)).not.toThrow();
  });

  it("rejects empty file (size 0)", () => {
    const file = new File([], "empty.jpg", { type: "image/jpeg" });
    expect(() => validateImageFile(file)).toThrow("Arquivo vazio ou corrompido");
  });

  it("rejects unsupported file type (GIF)", () => {
    const file = createMockFile("anim.gif", 1024, "image/gif");
    expect(() => validateImageFile(file)).toThrow("Tipo de arquivo não suportado");
  });

  it("rejects unsupported file type (PDF)", () => {
    const file = createMockFile("doc.pdf", 1024, "application/pdf");
    expect(() => validateImageFile(file)).toThrow("Tipo de arquivo não suportado");
  });

  it("rejects file exceeding 5MB limit", () => {
    const size = IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES + 1;
    const file = createMockFile("big.jpg", size, "image/jpeg");
    expect(() => validateImageFile(file)).toThrow("Arquivo muito grande");
  });

  it("accepts file exactly at 5MB limit", () => {
    const size = IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES;
    const file = createMockFile("max.jpg", size, "image/jpeg");
    expect(() => validateImageFile(file)).not.toThrow();
  });
});

describe("isRetryableError", () => {
  it("returns false for non-Axios errors", () => {
    expect(isRetryableError(new Error("generic"))).toBe(false);
  });

  it("returns false for 400 client error", () => {
    const error = {
      isAxiosError: true,
      response: { status: 400 },
    };
    // isRetryableError uses axios.isAxiosError which checks the flag
    expect(isRetryableError(error)).toBe(false);
  });

  it("returns false for 403 forbidden", () => {
    const error = {
      isAxiosError: true,
      response: { status: 403 },
    };
    expect(isRetryableError(error)).toBe(false);
  });

  it("returns false for null/undefined", () => {
    expect(isRetryableError(null)).toBe(false);
    expect(isRetryableError(undefined)).toBe(false);
  });
});
