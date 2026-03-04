import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { userService } from "@/services/userService";
import { tokenStorage } from "@/utils/tokenStorage";
import { useAuth } from "@/contexts/AuthContext";
import type { User } from "@/types/auth";

export function GoogleCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();

  useEffect(() => {
    let cancelled = false;

    async function checkSession() {
      try {
        const me = await userService.getCurrentUser();
        if (!cancelled) {
          const user: User = {
            id: me.id,
            email: me.email,
            full_name: me.full_name,
            birthday: me.birthday,
            cpf: me.cpf,
            picture: me.picture ?? "",
            is_active: true,
          };
          tokenStorage.saveUser(user);
          setUser(user);
          navigate("/", { replace: true });
        }
      } catch {
        if (!cancelled) {
          navigate("/login?error=oauth", { replace: true });
        }
      }
    }

    checkSession();
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
