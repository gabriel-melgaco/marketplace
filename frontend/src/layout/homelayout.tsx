import { Outlet } from "react-router-dom";
import Header from "../components/layout/Header";
import { BottomNav } from "../components/layout/BottomNav";
import { useAuth } from "@/contexts/AuthContext";
import { CompleteProfileModal } from "@/components/ui/CompleteProfileModal";

export default function HomeLayout() {
  const { user, isAuthenticated, setUser } = useAuth();

  const needsProfileCompletion =
    isAuthenticated && user && (!user.cpf || !user.birthday);

  return (
    <>
      <Header />
      <main>
        <Outlet />
      </main>
      <BottomNav />
      {needsProfileCompletion && (
        <CompleteProfileModal user={user} onComplete={setUser} />
      )}
    </>
  );
}
