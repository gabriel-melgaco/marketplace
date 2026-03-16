import axios from "axios";
import { API_BASE_URL } from "@/utils/constants";
import { tokenStorage } from "@/utils/tokenStorage";

const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string | null) => void;
  reject: (error: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't intercept 401 on auth endpoints (login, refresh, social auth, etc.)
    // Social auth endpoints must be excluded because the user has no tokens yet
    // when the OAuth callback exchange happens; intercepting would silently swallow
    // the real backend error and produce confusing retry behaviour.
    const authPaths = [
      "/auth/login/",
      "/auth/token/refresh/",
      "/auth/registration/",
      "/auth/social/",
    ];
    if (authPaths.some((path) => originalRequest.url?.includes(path))) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const refreshToken = tokenStorage.getRefreshToken();

    // No refresh token or refresh expired: clear tokens and retry without auth
    if (!refreshToken || tokenStorage.isRefreshTokenExpired()) {
      tokenStorage.clearTokens();
      delete originalRequest.headers.Authorization;
      return api(originalRequest);
    }

    // Try to refresh the access token
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        if (token) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        } else {
          delete originalRequest.headers.Authorization;
        }
        return api(originalRequest);
      });
    }

    isRefreshing = true;

    try {
      const response = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
        refresh: refreshToken,
      });

      const newAccessToken = response.data.access;
      tokenStorage.saveTokens({
        access: newAccessToken,
        refresh: response.data.refresh || refreshToken,
        access_expiration: response.data.access_expiration || "",
        refresh_expiration: response.data.refresh_expiration || "",
      });

      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      processQueue(null, newAccessToken);
      return api(originalRequest);
    } catch (refreshError) {
      // Refresh failed: clear tokens and retry without auth
      tokenStorage.clearTokens();
      processQueue(refreshError, null);
      delete originalRequest.headers.Authorization;
      return api(originalRequest);
    } finally {
      isRefreshing = false;
    }
  },
);

/**
 * Centralized token refresh shared between the axios interceptor and the
 * WebSocket reconnect path. Using a single function prevents the race
 * condition where both paths try to refresh the token simultaneously and
 * one of them caches stale data.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return null;

  // If a refresh is already in flight, wait for it to complete
  if (isRefreshing) {
    return new Promise((resolve) => {
      failedQueue.push({
        resolve: (token) => resolve(token),
        reject: () => resolve(null),
      });
    });
  }

  isRefreshing = true;
  try {
    const response = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
      refresh: refreshToken,
    });
    const newAccessToken = response.data.access;
    tokenStorage.saveTokens({
      access: newAccessToken,
      refresh: response.data.refresh || refreshToken,
      access_expiration: response.data.access_expiration || "",
      refresh_expiration: response.data.refresh_expiration || "",
    });
    processQueue(null, newAccessToken);
    return newAccessToken;
  } catch (err) {
    tokenStorage.clearTokens();
    processQueue(err, null);
    return null;
  } finally {
    isRefreshing = false;
  }
}

export default api;
