import { Link } from "react-router-dom";
import { ROUTES } from "@/routes/routePaths";

export function Footer() {
  return (
    <footer className="bg-gray-900 border-t border-gray-800 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-center sm:text-left">

          {/* Empresa */}
          <div>
            <p className="text-white text-sm font-semibold">
              GRUPO CHINA SOURCE TRADE LTDA
            </p>
            <p className="text-gray-400 text-xs mt-1">
              CNPJ: 44.933.523/0001-66
            </p>
            <p className="text-gray-400 text-xs mt-0.5">
              Av. Paulista, 171 — Bela Vista, São Paulo – SP
            </p>
          </div>

          {/* Links legais + Copyright */}
          <div className="flex flex-col items-center sm:items-end gap-2">
            <div className="flex items-center gap-4">
              <Link
                to={ROUTES.COOKIE_POLICY}
                className="text-gray-400 text-xs hover:text-gray-200 transition-colors"
              >
                Política de Cookies
              </Link>
            </div>
            <p className="text-gray-500 text-xs">
              © {new Date().getFullYear()} China Source Trade. Todos os direitos reservados.
            </p>
          </div>

        </div>
      </div>
    </footer>
  );
}
