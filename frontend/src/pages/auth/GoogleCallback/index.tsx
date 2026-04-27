import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { socialAuthService } from "@/services/socialAuthService";
import { tokenStorage } from "@/utils/tokenStorage";
import { useAuth } from "@/contexts/AuthContext";
import { userService } from "@/services/userService";
import type { User } from "@/types/auth";
import { AuthLogo } from "@/components/ui/AuthLogo";

export function GoogleCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();

  useEffect(() => {
    let cancelled = false;

    async function handleCallback() {
      const code = new URLSearchParams(window.location.search).get("code");

      if (!code) {
        navigate("/login?error=oauth", { replace: true });
        return;
      }

      try {
        const response = await socialAuthService.googleLogin({ code });
        if (!cancelled) {
          tokenStorage.saveUser(response.user);
          setUser(response.user);
          navigate("/", { replace: true });
        }
      } catch {
        // Última verificação — confirma se o cookie já autenticou o usuário
        try {
          const me = await userService.getCurrentUser();
          if (!cancelled) {
            const user: User = {
              id: me.id,
              email: me.email,
              full_name: me.full_name,
              birthday: me.birthday ?? "",
              cpf: me.cpf ?? "",
              picture: me.picture ?? "",
              is_active: true,
            };
            tokenStorage.saveUser(user);
            setUser(user);
            navigate("/", { replace: true });
          }
        } catch {
          // 401 confirmado — não está autenticado
          if (!cancelled) {
            navigate("/login?error=oauth", { replace: true });
          }
        }
      }
    }

    handleCallback();
    return () => {
      cancelled = true;
    };
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4 relative">
      <AuthLogo />

      {/* Card */}
      <div className="w-full max-w-md">
        <div className="bg-bg-1 border border-white/10 rounded-2xl overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]">
          <div
            className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center"
            role="status"
            aria-live="polite"
          >
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Loader2
                size={28}
                className="animate-spin text-gold"
                aria-hidden="true"
              />
            </div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
              Autenticando com Google
            </h1>
            <p className="text-ink-2 text-sm leading-relaxed">
              Aguarde um momento
            </p>
          </div>

          <div className="p-6 md:p-8 text-center">
            <p className="text-ink-2 text-sm leading-relaxed">
              Estamos validando suas credenciais. Você será redirecionado em
              instantes.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
