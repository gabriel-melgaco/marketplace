export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

export const MINIO_PUBLIC_URL =
  import.meta.env.VITE_MINIO_PUBLIC_URL || "http://localhost:9000";

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
};
