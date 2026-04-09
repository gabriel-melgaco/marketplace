import { NavHome } from "./NavHome";
import { NavSearch } from "./NavSearch";
import { NavCreate } from "./NavCreate";
import { NavChat } from "./NavChat";
import { NavMenu } from "./NavMenu";

export function BottomNav() {
  return (
    <div className="flex-shrink-0">
      <nav className="bg-black border-t shadow-lg z-40">
        <div className="max-w-7xl mx-auto flex justify-around items-center py-3">
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
