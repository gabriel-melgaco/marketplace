import axios from "axios";
import api from "@/api/axios";
import { MINIO_PUBLIC_URL } from "@/utils/constants";
import type { PresignedUrlRequest, PresignedUrlResponse } from "@/types/product";

export const IMAGE_UPLOAD_LIMITS = {
  ACCEPTED_TYPES: ["image/jpeg", "image/png", "image/webp"] as const,
  MAX_FILE_SIZE_BYTES: 5 * 1024 * 1024,
  MAX_FILE_SIZE_MB: 5,
} as const;

/**
 * Replaces internal Docker hostname (e.g. minio:9000) with the public
 * MinIO URL so the browser can actually reach the storage server.
 * Idempotent: returns the URL unchanged if it already uses the public host.
 * Preserves path and query params (critical for presigned URL signatures).
 */
export function toPublicUrl(url: string): string {
  if (!url) return url;

  try {
    const parsed = new URL(url);
    const pub = new URL(MINIO_PUBLIC_URL);

    // Already using the public MinIO host — nothing to do.
    if (parsed.hostname === pub.hostname && parsed.port === pub.port) {
      return url;
    }

    // Only convert URLs from internal Docker hostnames (bare names without
    // dots, e.g. "minio"). External URLs (e.g. "alcateiafitness.com.br")
    // must be left untouched.
    const isInternalHost = !parsed.hostname.includes(".");
    if (!isInternalHost) {
      return url;
    }

    parsed.protocol = pub.protocol;
    parsed.hostname = pub.hostname;
    parsed.port = pub.port;
    return parsed.toString();
  } catch {
    console.warn("[StorageService] Failed to parse URL:", url);
    return url;
  }
}

export function validateImageFile(file: File): void {
  if (!file.size) {
    throw new Error("Arquivo vazio ou corrompido.");
  }
  if (
    !IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES.includes(
      file.type as (typeof IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES)[number],
    )
  ) {
    throw new Error(
      `Tipo de arquivo não suportado: ${file.type}. Use JPEG, PNG ou WebP.`,
    );
  }
  if (file.size > IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES) {
    throw new Error(
      `Arquivo muito grande (${(file.size / 1024 / 1024).toFixed(1)}MB). Máximo ${IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB.`,
    );
  }
}

const S3_UPLOAD_TIMEOUT_MS = 120_000;
const S3_MAX_RETRIES = 3;
const S3_INITIAL_DELAY_MS = 1000;

export function isRetryableError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  const status = error.response?.status;
  // Retry on network errors (no response) or server errors (5xx)
  return !status || status >= 500;
}

async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = S3_MAX_RETRIES,
  initialDelay: number = S3_INITIAL_DELAY_MS,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt >= maxRetries || !isRetryableError(error)) {
        throw error;
      }
      const delay = initialDelay * Math.pow(2, attempt);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw lastError;
}

export const storageService = {
  /**
   * Requests a presigned PUT URL from the backend.
   * Both returned URLs are converted to the public MinIO endpoint.
   */
  async getPresignedUrl(
    fileName: string,
    contentType: string,
  ): Promise<PresignedUrlResponse> {
    const response = await api.post<PresignedUrlResponse>(
      "/storage/upload/presigned-url/",
      { file_name: fileName, content_type: contentType } as PresignedUrlRequest,
    );

    const { upload_url, file_url, object_name } = response.data;

    if (!object_name?.trim()) {
      throw new Error(
        "Servidor não retornou object_name válido. Tente novamente.",
      );
    }

    return {
      upload_url: toPublicUrl(upload_url),
      file_url: toPublicUrl(file_url),
      object_name,
    };
  },

  /**
   * Uploads a file directly to MinIO/S3 using the presigned URL.
   *
   * Uses raw axios (not the `api` instance) because:
   * - Presigned URLs already contain authentication in query params
   * - Adding baseURL would break the full S3 URL
   * - Adding Authorization header would cause S3 to reject the request
   */
  async uploadToS3(
    uploadUrl: string,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<void> {
    try {
      await withRetry(() =>
        axios.put(uploadUrl, file, {
          headers: { "Content-Type": file.type },
          timeout: S3_UPLOAD_TIMEOUT_MS,
          onUploadProgress: (e) => {
            if (onProgress && e.total) {
              onProgress(Math.round((e.loaded * 100) / e.total));
            }
          },
        }),
      );
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const status = error.response?.status;
        throw new Error(
          `Upload falhou para "${file.name}" (status ${status ?? "network error"})`,
        );
      }
      throw error;
    }
  },

  /**
   * High-level helper: validates file, gets presigned URL, uploads,
   * and returns the public file_url for storage.
   */
  async uploadImage(
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<string> {
    validateImageFile(file);

    const contentType = file.type;
    const fileName = file.name;

    const { upload_url, file_url } = await this.getPresignedUrl(
      fileName,
      contentType,
    );

    await this.uploadToS3(upload_url, file, onProgress);

    return file_url;
  },
};
