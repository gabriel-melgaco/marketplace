import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { CgClose } from "react-icons/cg";
import { TiShoppingCart } from "react-icons/ti";
import { Plus, Minus, Trash2, ShoppingBag } from "lucide-react";
import { useCart } from "@/contexts/CartContext";
import { toPublicUrl } from "@/services/storageService";

function formatPrice(price: string): string {
  const num = Number(price);
  if (isNaN(num)) return price;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
}

export function CartDrawer() {
  const [isOpen, setIsOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const { items, totalItems, updateQuantity, removeFromCart } = useCart();

  const totalPrice = items.reduce(
    (sum, item) => sum + Number(item.listing.price) * item.quantity,
    0,
  );

  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="relative text-ink-2 hover:text-ink-1 p-2 rounded-xl border border-transparent hover:bg-bg-2 hover:border-white/[0.12] transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
        aria-label={`Abrir carrinho de compras${totalItems > 0 ? `, ${totalItems} ${totalItems === 1 ? "item" : "itens"}` : ""}`}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
      >
        <TiShoppingCart className="w-7 h-7 md:w-8 md:h-8" aria-hidden="true" />
        {totalItems > 0 && (
          <span
            aria-hidden="true"
            className="absolute -top-1.5 -right-1.5 min-w-4.5 h-4.5 bg-gold text-gold-deep ring-2 ring-bg-0 text-xs font-bold rounded-full flex items-center justify-center px-1 leading-none"
          >
            {totalItems > 99 ? "99+" : totalItems}
          </span>
        )}
      </button>

      {createPortal(
        <>
          <div
            className={`
              fixed inset-0 z-9998 bg-black/60 transition-opacity
              ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}
            `}
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />

          <aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="cart-drawer-heading"
            className={`
              fixed top-0 bottom-0 right-0 z-9999
              w-3/4 md:w-1/2 lg:w-1/3
              bg-bg-1 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)]
              transform transition-transform duration-300
              ${isOpen ? "translate-x-0" : "translate-x-full"}
              flex flex-col
            `}
          >
            <div className="flex items-center justify-between px-4 py-4 border-b border-white/10">
              <h2
                id="cart-drawer-heading"
                className="font-semibold text-lg text-ink-1"
              >
                Carrinho
                {totalItems > 0 && (
                  <span className="ml-2 text-sm font-normal text-ink-3">
                    ({totalItems} {totalItems === 1 ? "item" : "itens"})
                  </span>
                )}
              </h2>
              <button
                ref={closeButtonRef}
                onClick={() => setIsOpen(false)}
                aria-label="Fechar carrinho"
                className="w-9 h-9 flex items-center justify-center rounded-xl text-ink-3 hover:text-ink-1 hover:bg-bg-3 active:bg-bg-3 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
              >
                <CgClose className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <div
              className="flex-1 overflow-y-auto"
              aria-live="polite"
              aria-label="Itens no carrinho"
            >
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-3 px-6 text-center py-16">
                  <div className="w-16 h-16 rounded-2xl bg-bg-2 border border-white/10 flex items-center justify-center">
                    <ShoppingBag
                      size={28}
                      className="text-ink-3"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="font-semibold text-ink-1 text-sm">
                    Carrinho vazio
                  </p>
                  <p className="text-ink-3 text-xs max-w-45 leading-relaxed">
                    Adicione produtos para começar suas compras.
                  </p>
                </div>
              ) : (
                <ul
                  className="divide-y divide-white/[0.06]"
                  aria-label="Lista de itens"
                >
                  {items.map((item) => {
                    const imgs = item.listing.images;
                    const primaryImg =
                      imgs?.find((i) => i.is_primary) ?? imgs?.[0];
                    const imgSrc = primaryImg
                      ? toPublicUrl(primaryImg.image_url)
                      : null;

                    const productName =
                      item.listing.title || item.listing.product.name;

                    return (
                      <li key={item.listing.id} className="flex gap-3 p-4">
                        <div className="w-16 h-16 bg-bg-2 rounded-xl border border-white/[0.06] overflow-hidden shrink-0">
                          {imgSrc ? (
                            <img
                              src={imgSrc}
                              alt={productName}
                              className="w-full h-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <ShoppingBag
                                size={18}
                                className="text-ink-3"
                                aria-hidden="true"
                              />
                            </div>
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-ink-1 truncate leading-tight">
                            {productName}
                          </p>
                          <p className="text-sm font-bold text-gold mt-0.5">
                            R$ {formatPrice(item.listing.price)}
                          </p>

                          <div className="flex items-center gap-2 mt-2">
                            <button
                              type="button"
                              onClick={() =>
                                updateQuantity(
                                  item.listing.id,
                                  item.quantity - 1,
                                )
                              }
                              disabled={item.quantity <= 1}
                              className="w-7 h-7 rounded-lg border border-white/10 flex items-center justify-center text-ink-2 hover:bg-bg-3 active:bg-bg-3 transition disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
                              aria-label={`Diminuir quantidade de ${productName}`}
                            >
                              <Minus size={12} aria-hidden="true" />
                            </button>
                            <span
                              className="text-sm font-medium text-ink-1 min-w-6 text-center"
                              aria-label={`Quantidade: ${item.quantity}`}
                            >
                              {item.quantity}
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                updateQuantity(
                                  item.listing.id,
                                  item.quantity + 1,
                                )
                              }
                              disabled={item.quantity >= item.listing.quantity}
                              className="w-7 h-7 rounded-lg border border-white/10 flex items-center justify-center text-ink-2 hover:bg-bg-3 active:bg-bg-3 transition disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
                              aria-label={`Aumentar quantidade de ${productName}`}
                            >
                              <Plus size={12} aria-hidden="true" />
                            </button>

                            <button
                              type="button"
                              onClick={() => removeFromCart(item.listing.id)}
                              className="ml-auto w-7 h-7 rounded-lg flex items-center justify-center text-ink-3 hover:text-red-400 hover:bg-red-500/10 active:bg-red-500/20 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/40"
                              aria-label={`Remover ${productName} do carrinho`}
                            >
                              <Trash2 size={13} aria-hidden="true" />
                            </button>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {items.length > 0 && (
              <div className="border-t border-white/10 bg-bg-1 px-4 py-4 space-y-3">
                <div className="flex justify-between">
                  <span className="text-ink-1 font-semibold">Subtotal</span>
                  <span className="text-ink-1 font-bold">R$ {formatPrice(String(totalPrice))}</span>
                </div>
                <p className="text-ink-3 text-xs mt-1">
                  Frete calculado no checkout
                </p>
                <Link
                  to="/checkout"
                  onClick={() => setIsOpen(false)}
                  className="block w-full text-center px-4 py-3 bg-gold text-gold-deep font-semibold rounded-xl hover:bg-gold/90 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
                >
                  Finalizar Compra
                </Link>
              </div>
            )}
          </aside>
        </>,
        document.body,
      )}
    </>
  );
}
