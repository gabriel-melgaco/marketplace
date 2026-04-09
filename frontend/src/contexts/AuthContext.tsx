import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { authService } from "@/services/authService";
import { userService } from "@/services/userService";
import { tokenStorage } from "@/utils/tokenStorage";
import type { AuthContextData, User, LoginCredentials } from "@/types/auth";

// Criar o contexto e EXPORTAR
export const AuthContext = createContext<AuthContextData | undefined>(
  undefined,
);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  // Verificar autenticação ao carregar
  useEffect(() => {
    const checkAuth = async () => {
      if (!authService.isAuthenticated()) {
        setIsLoading(false);
        return;
      }

      try {
        const freshUser = await userService.getCurrentUser();
        tokenStorage.saveUser(freshUser);
        setUser(freshUser as unknown as User);
      } catch {
        const currentUser = authService.getCurrentUser();
        setUser(currentUser);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Função de login
  async function login(credentials: LoginCredentials) {
    try {
      const response = await authService.login(credentials);
      setUser(response.user);
    } catch (error) {
      throw error; // Propagar erro para o componente
    }
  }

  // Função de logout
  function logout() {
    authService.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, isLoading, login, logout, setUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// Hook customizado para usar o contexto
export function useAuth(): AuthContextData {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
