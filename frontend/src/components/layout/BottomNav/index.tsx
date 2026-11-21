import { NavHome } from "./NavHome";
import { NavSearch } from "./NavSearch";
import { NavCreate } from "./NavCreate";
import { NavChat } from "./NavChat";
import { NavMenu } from "./NavMenu";

export function BottomNav() {
  return (
    <div className="flex-shrink-0">
      <nav
        className="bg-bg-0/90 backdrop-blur-2xl border-t border-white/[0.06] z-40"
        style={{ paddingBottom: 'calc(0.625rem + env(safe-area-inset-bottom))' }}
      >
        <div className="max-w-7xl mx-auto grid grid-cols-5 pt-2.5">
          <NavHome />
          <NavSearch />
          <NavCreate />
          <NavChat />
          <NavMenu />
        </div>
      </nav>
    </div>
  );
}
