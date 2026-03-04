import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { socialAuthService } from "@/services/socialAuthService";
import { tokenStorage } from "@/utils/tokenStorage";
import { useAuth } from "@/contexts/AuthContext";

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
        if (!cancelled) {
          navigate("/login?error=oauth", { replace: true });
        }
      }
    }

    handleCallback();
    return () => {
      cancelled = true;
    };
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4" />
        <p className="text-white text-lg">Autenticando com Google...</p>
      </div>
    </div>
  );
}
