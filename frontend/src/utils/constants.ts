export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

export const MINIO_PUBLIC_URL =
  import.meta.env.VITE_MINIO_PUBLIC_URL || "http://localhost:9000";

export const GOOGLE_CLIENT_ID =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  "111464785891-0gt867f9asiqnf6m58g0rmm3gvm15uuh.apps.googleusercontent.com";

export const GOOGLE_REDIRECT_URI =
  import.meta.env.VITE_GOOGLE_REDIRECT_URI ||
  "http://localhost:5173/auth/google/callback";

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
};
