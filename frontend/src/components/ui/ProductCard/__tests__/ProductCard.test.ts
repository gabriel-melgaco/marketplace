import { describe, it, expect, vi } from "vitest";
import type { MarketplaceListing } from "@/types/product";

// Mock constants before any module that imports them
vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test",
  GOOGLE_REDIRECT_URI: "http://localhost:5173/auth/google/callback",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

import { formatListingDate, getListingLocation, getImageSrc } from "../index";

function makeListing(
  overrides: Partial<MarketplaceListing> = {},
): MarketplaceListing {
  return {
    id: 1,
    product: { id: 1, name: "Esteira", slug: "esteira", code: null },
    seller: 1,
    seller_name: "João",
    title: "Esteira Movement R3",
    price: "1500.00",
    brand: { id: 1, name: "Movement", slug: "movement", logo: null },
    quantity: 1,
    is_active: true,
    description: "Em ótimo estado",
    condition: { id: 1, name: "Usado", slug: "usado" },
    views_count: 10,
    created_at: "2025-06-15T10:30:00Z",
    updated_at: "2025-06-15T10:30:00Z",
    sold_at: null,
    images: [],
    primary_image: null,
    shipping_address: null,
    ...overrides,
  };
}

describe("formatListingDate", () => {
  it("formats date as DD/MM/YYYY", () => {
    const result = formatListingDate("2025-06-15T10:30:00Z");
    expect(result).toMatch(/^\d{2}\/\d{2}\/\d{4}$/);
    expect(result).toContain("2025");
  });

  it("returns 'Data inválida' for invalid date", () => {
    expect(formatListingDate("invalid")).toBe("Data inválida");
    expect(formatListingDate("")).toBe("Data inválida");
  });

  it("uses 4-digit year (not 2-digit)", () => {
    const result = formatListingDate("2025-01-05T00:00:00Z");
    expect(result).toContain("2025");
    expect(result).not.toMatch(/\/25$/);
  });
});

describe("getListingLocation", () => {
  it("returns empty string when no shipping address", () => {
    const listing = makeListing({ shipping_address: null });
    expect(getListingLocation(listing)).toBe("");
  });

  it("returns city and state when shipping address exists", () => {
    const listing = makeListing({
      shipping_address: { id: 1, city: "São Paulo", state: "SP" },
    });
    expect(getListingLocation(listing)).toBe("São Paulo - SP");
  });
});

describe("getImageSrc", () => {
  it("returns null when no images at all", () => {
    const listing = makeListing({ primary_image: null, images: [] });
    expect(getImageSrc(listing)).toBeNull();
  });

  it("uses primary_image when available", () => {
    const listing = makeListing({
      primary_image: "http://localhost:9000/bucket/img.jpg",
      images: [],
    });
    expect(getImageSrc(listing)).toBe("http://localhost:9000/bucket/img.jpg");
  });

  it("falls back to first image from images array when primary_image is null", () => {
    const listing = makeListing({
      primary_image: null,
      images: [
        {
          id: 1,
          image_url: "http://localhost:9000/bucket/fallback.jpg",
          object_name: "test.jpg",
          is_primary: false,
          order: 0,
          created_at: "2025-06-15T10:30:00Z",
        },
      ],
    });
    expect(getImageSrc(listing)).toBe(
      "http://localhost:9000/bucket/fallback.jpg",
    );
  });

  it("prefers is_primary image from images array over first image", () => {
    const listing = makeListing({
      primary_image: null,
      images: [
        {
          id: 1,
          image_url: "http://localhost:9000/bucket/first.jpg",
          object_name: "first.jpg",
          is_primary: false,
          order: 0,
          created_at: "2025-06-15T10:30:00Z",
        },
        {
          id: 2,
          image_url: "http://localhost:9000/bucket/primary.jpg",
          object_name: "primary.jpg",
          is_primary: true,
          order: 1,
          created_at: "2025-06-15T10:30:00Z",
        },
      ],
    });
    expect(getImageSrc(listing)).toBe(
      "http://localhost:9000/bucket/primary.jpg",
    );
  });

  it("converts internal Docker URL to public URL", () => {
    const listing = makeListing({
      primary_image: "http://minio:9000/bucket/img.jpg",
      images: [],
    });
    const src = getImageSrc(listing);
    // Should be converted to localhost:9000 (the public URL)
    expect(src).toBe("http://localhost:9000/bucket/img.jpg");
  });

  it("converts internal Docker URL in images array", () => {
    const listing = makeListing({
      primary_image: null,
      images: [
        {
          id: 1,
          image_url: "http://minio:9000/bucket/img.jpg",
          object_name: "img.jpg",
          is_primary: false,
          order: 0,
          created_at: "2025-06-15T10:30:00Z",
        },
      ],
    });
    const src = getImageSrc(listing);
    expect(src).toBe("http://localhost:9000/bucket/img.jpg");
  });
});

describe("getImageSrc - edge cases", () => {
  it("primary_image takes precedence over is_primary in images array", () => {
    const listing = makeListing({
      primary_image: "http://localhost:9000/bucket/primary_field.jpg",
      images: [
        {
          id: 1,
          image_url: "http://localhost:9000/bucket/array_primary.jpg",
          object_name: "array_primary.jpg",
          is_primary: true,
          order: 0,
          created_at: "2025-06-15T10:30:00Z",
        },
      ],
    });
    expect(getImageSrc(listing)).toBe(
      "http://localhost:9000/bucket/primary_field.jpg",
    );
  });

  it("returns first image by array index when none are is_primary", () => {
    const listing = makeListing({
      primary_image: null,
      images: [
        {
          id: 10,
          image_url: "http://localhost:9000/bucket/first.jpg",
          object_name: "first.jpg",
          is_primary: false,
          order: 5,
          created_at: "2025-06-15T10:30:00Z",
        },
        {
          id: 11,
          image_url: "http://localhost:9000/bucket/second.jpg",
          object_name: "second.jpg",
          is_primary: false,
          order: 0,
          created_at: "2025-06-15T10:30:00Z",
        },
      ],
    });
    expect(getImageSrc(listing)).toBe(
      "http://localhost:9000/bucket/first.jpg",
    );
  });

  it("handles images array with undefined gracefully", () => {
    const listing = makeListing({
      primary_image: null,
      images: undefined as any,
    });
    expect(getImageSrc(listing)).toBeNull();
  });
});

describe("ProductCard subtitle", () => {
  it("builds subtitle with date and location", () => {
    const listing = makeListing({
      created_at: "2025-06-15T10:30:00Z",
      shipping_address: { id: 1, city: "São Paulo", state: "SP" },
    });
    const date = formatListingDate(listing.created_at);
    const location = getListingLocation(listing);
    const subtitle = location
      ? `Publicado em ${date} - ${location}`
      : `Publicado em ${date}`;
    expect(subtitle).toMatch(/^Publicado em \d{2}\/\d{2}\/\d{4} - São Paulo - SP$/);
  });

  it("builds subtitle without location when address is null", () => {
    const listing = makeListing({
      created_at: "2025-06-15T10:30:00Z",
      shipping_address: null,
    });
    const date = formatListingDate(listing.created_at);
    const location = getListingLocation(listing);
    const subtitle = location
      ? `Publicado em ${date} - ${location}`
      : `Publicado em ${date}`;
    expect(subtitle).toMatch(/^Publicado em \d{2}\/\d{2}\/\d{4}$/);
    expect(subtitle).not.toContain(" - ");
  });

  it("displays listing title instead of product name", () => {
    const listing = makeListing({
      title: "Esteira Elétrica Seminova",
      product: { id: 1, name: "Esteira", slug: "esteira", code: null },
    });
    const displayTitle = listing.title || listing.product.name;
    expect(displayTitle).toBe("Esteira Elétrica Seminova");
  });

  it("falls back to product name when title is empty", () => {
    const listing = makeListing({
      title: "",
      product: { id: 1, name: "Esteira", slug: "esteira", code: null },
    });
    const displayTitle = listing.title || listing.product.name;
    expect(displayTitle).toBe("Esteira");
  });
});
