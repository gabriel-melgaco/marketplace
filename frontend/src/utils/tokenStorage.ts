interface TokenData {
  access: string;
  refresh: string;
  access_expiration: string;
  refresh_expiration: string;
}

const ACCESS_TOKEN_KEY = "@access_token";
const REFRESH_TOKEN_KEY = "@refresh_token";
const TOKEN_DATA_KEY = "@token_data";
const USER_KEY = "@user_data";

export const tokenStorage = {
  saveTokens(data: TokenData): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh);
    localStorage.setItem(TOKEN_DATA_KEY, JSON.stringify(data));
  },

  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },

  getTokenData(): TokenData | null {
    const data = localStorage.getItem(TOKEN_DATA_KEY);
    if (!data) return null;

    try {
      return JSON.parse(data);
    } catch {
      return null;
    }
  },

  isAccessTokenExpired(): boolean {
    const tokenData = this.getTokenData();
    if (!tokenData) return true;

    try {
      const expirationDate = new Date(tokenData.access_expiration);
      return expirationDate <= new Date();
    } catch {
      return true;
    }
  },

  isRefreshTokenExpired(): boolean {
    const tokenData = this.getTokenData();
    if (!tokenData) return true;

    try {
      const expirationDate = new Date(tokenData.refresh_expiration);
      return expirationDate <= new Date();
    } catch {
      return true;
    }
  },

  saveUser(user: any): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  getUser(): any | null {
    const data = localStorage.getItem(USER_KEY);
    if (!data) return null;

    try {
      return JSON.parse(data);
    } catch {
      return null;
    }
  },

  clearAll(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(TOKEN_DATA_KEY);
    localStorage.removeItem(USER_KEY);
  },

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(TOKEN_DATA_KEY);
  },
};
