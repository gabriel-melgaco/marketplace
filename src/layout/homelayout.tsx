import { Outlet } from "react-router-dom";
import Header from "../components/layout/Header";
import { BottomNav } from "../components/layout/BottomNav";

export default function HomeLayout() {
  return (
    <>
      <Header />
      <main>
        <Outlet />
      </main>
      <BottomNav />
    </>
  );
}
