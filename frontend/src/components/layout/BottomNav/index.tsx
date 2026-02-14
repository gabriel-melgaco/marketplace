import { NavHome } from "./NavHome";
import { NavSearch } from "./NavSearch";
import { NavCreate } from "./NavCreate";
import { NavChat } from "./NavChat";
import { NavMenu } from "./NavMenu";

export function BottomNav() {
  return (
    <div>
      <nav className="fixed bottom-0 left-0 right-0 bg-black border-t shadow-lg">
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
