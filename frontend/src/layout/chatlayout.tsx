import { Outlet } from "react-router-dom";
import Header from "../components/layout/Header";
import { BottomNav } from "../components/layout/BottomNav";
import { useAuth } from "@/contexts/AuthContext";
import { CompleteProfileModal } from "@/components/ui/CompleteProfileModal";

/**
 * Layout exclusivo para as rotas de chat (/conversations e /conversations/:id).
 *
 * Diferente do HomeLayout, o <main> aqui é overflow-hidden e h-full, para que
 * componentes filhos como ConversationDetail possam controlar o próprio scroll
 * internamente sem que a página inteira role.
 *
 * Estrutura:
 *   div.flex.flex-col.h-dvh
 *     Header  (flex-shrink-0, sticky)
 *     main    (flex-1, overflow-hidden, min-h-0)
 *     BottomNav (sticky bottom-0)
 */
export default function ChatLayout() {
  const { user, isAuthenticated, setUser } = useAuth();

  const needsProfileCompletion =
    isAuthenticated && user && (!user.cpf || !user.birthday);

  return (
    <div className="flex flex-col h-dvh min-h-screen">
      <Header />
      <main className="flex-1 overflow-hidden min-h-0 flex flex-col">
        <Outlet />
      </main>
      <BottomNav />
      {needsProfileCompletion && (
        <CompleteProfileModal user={user} onComplete={setUser} />
      )}
    </div>
  );
}
