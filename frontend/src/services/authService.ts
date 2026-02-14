import api from "@/api/axios";
import { tokenStorage } from "@/utils/tokenStorage";
import type {
  LoginCredentials,
  LoginResponse,
  RegisterCredentials,
  RegisterResponse,
  PasswordChangeRequest,
  PasswordResetRequest,
  PasswordResetConfirmRequest,
  ResendEmailRequest,
  VerifyEmailRequest,
  ApiResponse,
} from "@/types/auth";

export const authService = {
  // ============================================
  // LOGIN
  // ============================================

  async login(credentials: LoginCredentials): Promise<LoginResponse> {
    try {
      const response = await api.post<LoginResponse>(
        "/auth/login/",
        credentials,
      );

      tokenStorage.saveTokens({
        access: response.data.access,
        refresh: response.data.refresh,
        access_expiration: response.data.access_expiration,
        refresh_expiration: response.data.refresh_expiration,
      });

      tokenStorage.saveUser(response.data.user);

      return response.data;
    } catch (error: any) {
      if (error.response?.status === 401) {
        throw new Error("Email ou senha incorretos");
      }
      if (error.response?.status === 400) {
        throw new Error("Dados inválidos");
      }
      throw new Error("Erro ao fazer login. Tente novamente.");
    }
  },

  // ============================================
  // LOGOUT
  // ============================================

  async logout(): Promise<void> {
    try {
      const refreshToken = tokenStorage.getRefreshToken();

      if (refreshToken) {
        await api.post("/auth/logout/", { refresh: refreshToken });
      }
    } catch (error) {
      console.error("Erro ao fazer logout na API:", error);
    } finally {
      tokenStorage.clearAll();
    }
  },

  // ============================================
  // REGISTRO - COM DEBUG
  // ============================================

  async register(credentials: RegisterCredentials): Promise<RegisterResponse> {
    try {
      // ⭐ LOG 1: Ver o que estamos enviando
      console.log("📤 ENVIANDO PARA API:", credentials);

      const response = await api.post<RegisterResponse>(
        "/auth/registration/",
        credentials,
      );

      // ⭐ LOG 2: Ver o que recebemos de volta
      console.log("✅ RESPOSTA DA API:", response.data);

      return response.data;
    } catch (error: any) {
      // ⭐ LOG 3: Ver o erro completo
      console.error("❌ ERRO COMPLETO:", error);
      console.error("❌ ERRO RESPONSE:", error.response);
      console.error("❌ ERRO DATA:", error.response?.data);
      console.error("❌ ERRO STATUS:", error.response?.status);

      // Verificar se é erro 400
      if (error.response?.status === 400) {
        // ⭐ Pegar a mensagem específica da API
        const apiError = error.response?.data;

        // Se a API retornou um objeto com campos
        if (typeof apiError === "object") {
          // Pegar o primeiro erro de campo
          const firstError = Object.values(apiError)[0];

          if (Array.isArray(firstError)) {
            throw new Error(firstError[0]);
          }

          if (typeof firstError === "string") {
            throw new Error(firstError);
          }
        }

        // Se tem detail
        if (apiError?.detail) {
          throw new Error(apiError.detail);
        }

        throw new Error("Dados inválidos. Verifique os campos.");
      }

      // Outros erros
      throw new Error("Erro ao criar conta. Tente novamente.");
    }
  },

  // ============================================
  // OUTRAS FUNÇÕES
  // ============================================

  async resendVerificationEmail(
    data: ResendEmailRequest,
  ): Promise<ApiResponse> {
    try {
      const response = await api.post<ApiResponse>(
        "/auth/registration/resend-email/",
        data,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || "Erro ao reenviar email");
    }
  },

  async verifyEmail(data: VerifyEmailRequest): Promise<ApiResponse> {
    try {
      const response = await api.post<ApiResponse>(
        "/auth/registration/verify-email/",
        data,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(
        error.response?.data?.detail || "Erro ao verificar email",
      );
    }
  },

  async changePassword(data: PasswordChangeRequest): Promise<ApiResponse> {
    try {
      const response = await api.post<ApiResponse>(
        "/auth/password/change/",
        data,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || "Erro ao alterar senha");
    }
  },

  async requestPasswordReset(data: PasswordResetRequest): Promise<ApiResponse> {
    try {
      const response = await api.post<ApiResponse>(
        "/auth/password/reset/",
        data,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(
        error.response?.data?.detail || "Erro ao solicitar reset de senha",
      );
    }
  },

  async confirmPasswordReset(
    data: PasswordResetConfirmRequest,
  ): Promise<ApiResponse> {
    try {
      const response = await api.post<ApiResponse>(
        "/auth/password/reset/confirm/",
        data,
      );
      return response.data;
    } catch (error: any) {
      throw new Error(
        error.response?.data?.detail || "Erro ao redefinir senha",
      );
    }
  },

  isAuthenticated(): boolean {
    const accessToken = tokenStorage.getAccessToken();
    return !!accessToken && !tokenStorage.isAccessTokenExpired();
  },

  getCurrentUser() {
    return tokenStorage.getUser();
  },

  needsTokenRefresh(): boolean {
    return (
      tokenStorage.isAccessTokenExpired() &&
      !tokenStorage.isRefreshTokenExpired()
    );
  },

  // ============================================
  // TOKEN REFRESH
  // ============================================

  async refreshToken(): Promise<{ access: string; refresh?: string }> {
    try {
      const refreshToken = tokenStorage.getRefreshToken();
      if (!refreshToken) {
        throw new Error("No refresh token available");
      }

      const response = await api.post<{ access: string; refresh?: string }>(
        "/auth/token/refresh/",
        { refresh: refreshToken },
      );

      // Update stored access token
      if (response.data.access) {
        tokenStorage.saveTokens({
          access: response.data.access,
          refresh: response.data.refresh || refreshToken,
          access_expiration: "", // Will be updated by backend
          refresh_expiration: "", // Will be updated by backend
        });
      }

      return response.data;
    } catch (error: any) {
      // If refresh fails, clear tokens and force re-login
      tokenStorage.clearAll();
      throw new Error("Session expired. Please login again.");
    }
  },

  async verifyToken(token: string): Promise<boolean> {
    try {
      await api.post("/auth/token/verify/", { token });
      return true;
    } catch (error) {
      return false;
    }
  },
};
