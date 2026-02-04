import React, { useState, useRef, type MouseEvent } from "react";
import { ChevronDown, Package } from "lucide-react";

// Tipos
interface Product {
  image?: string;
  title: string;
  price: string;
  location: string;
  time: string;
}

// Componente de Card de Produto
const ProductCard: React.FC<Product> = ({
  image,
  title,
  price,
  location,
  time,
}) => {
  return (
    <div className="shrink-0 w-72 bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition-shadow">
      <div className="h-48 bg-gray-200 flex items-center justify-center">
        {image ? (
          <img src={image} alt={title} className="w-full h-full object-cover" />
        ) : (
          <div className="text-gray-400 text-center p-4">
            <Package size={48} className="mx-auto mb-2" />
            <p className="text-sm">Adicione uma imagem</p>
          </div>
        )}
      </div>
      <div className="p-4">
        <h3 className="font-semibold text-gray-800 mb-2 truncate">{title}</h3>
        <p className="text-2xl font-bold text-blue-800 mb-1">R${price}</p>
        <p className="text-xs text-gray-500 truncate">
          {time} - {location}
        </p>
      </div>
    </div>
  );
};

// Componente de Carrossel
interface CarouselProps {
  title: string;
  products: Product[];
}

const ProductCarousel: React.FC<CarouselProps> = ({ title, products }) => {
  const carouselRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [startX, setStartX] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);

  const handleMouseDown = (e: MouseEvent<HTMLDivElement>) => {
    if (!carouselRef.current) return;
    setIsDragging(true);
    setStartX(e.pageX - carouselRef.current.offsetLeft);
    setScrollLeft(carouselRef.current.scrollLeft);
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!isDragging || !carouselRef.current) return;
    e.preventDefault();
    const x = e.pageX - carouselRef.current.offsetLeft;
    const walk = (x - startX) * 2;
    carouselRef.current.scrollLeft = scrollLeft - walk;
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  return (
    <div className="mb-8">
      <h2 className="text-xl font-bold text-white mb-4 px-4">{title}</h2>
      <div
        ref={carouselRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className="flex gap-4 overflow-x-auto scrollbar-hide px-4 cursor-grab active:cursor-grabbing"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {products.map((product, index) => (
          <ProductCard key={index} {...product} />
        ))}
      </div>
    </div>
  );
};

// Componente Principal
export default function MarketplaceHome() {
  const [categoryOpen, setCategoryOpen] = useState(false);

  const recentProducts: Product[] = [
    {
      title: "Estação de Musculação",
      price: "2.800,00",
      time: "Hoje às 18:00",
      location: "Pindamonhangaba-SP",
    },
    {
      title: "Kit Academia Completa",
      price: "3.600,00",
      time: "Hoje às 09:00",
      location: "Balneário Camboriú-SC",
    },
    {
      title: "Barra Olímpica Profissional",
      price: "850,00",
      time: "Ontem às 15:30",
      location: "São Paulo-SP",
    },
    {
      title: "Rack de Agachamento",
      price: "1.900,00",
      time: "Ontem às 12:00",
      location: "Rio de Janeiro-RJ",
    },
  ];

  const promoProducts: Product[] = [
    {
      title: "Aparelho Abdominal",
      price: "1.200,00",
      time: "23/12/25 às 13:00",
      location: "Belém-PA",
    },
    {
      title: "Aparelho Remador Seco Hidráulico",
      price: "2.200,00",
      time: "18/11/25 às 18:00",
      location: "Manaus-AM",
    },
    {
      title: "Bicicleta Ergométrica",
      price: "1.550,00",
      time: "20/12/25 às 10:00",
      location: "Curitiba-PR",
    },
    {
      title: "Step Profissional",
      price: "380,00",
      time: "22/12/25 às 14:00",
      location: "Fortaleza-CE",
    },
  ];

  const popularProducts: Product[] = [
    {
      title: "Desenvolvimento de Ombros",
      price: "3.450,00",
      time: "15/12/25 às 09:00",
      location: "Brasília-DF",
    },
    {
      title: "Esteira Ergométrica Motorizada",
      price: "4.800,00",
      time: "10/12/25 às 16:00",
      location: "Porto Alegre-RS",
    },
    {
      title: "Conjunto de Halteres",
      price: "2.100,00",
      time: "12/12/25 às 11:00",
      location: "Belo Horizonte-MG",
    },
    {
      title: "Leg Press 45º",
      price: "5.200,00",
      time: "08/12/25 às 13:30",
      location: "Salvador-BA",
    },
  ];

  return (
    <div className="min-h-screen bg-linear-to-br from-black via-gray-900 to-blue-600">
      {/* Menu Suspenso (Estado) */}
      <div className="bg-transparent">
        <div className="max-w-7xl mx-3 d:mx-13">
          <button
            onClick={() => setCategoryOpen(!categoryOpen)}
            className="flex items-center gap-2 px-4 py-2 bg-white border-2 border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            Estado <ChevronDown size={20} />
          </button>
        </div>
      </div>

      {/* Conteúdo Principal - Carrosséis */}
      <main className="max-w-7xl mx-auto py-8 pb-24">
        <ProductCarousel
          title="Adicionados Recentemente"
          products={recentProducts}
        />
        <ProductCarousel
          title="Produtos na Promoção"
          products={promoProducts}
        />
        <ProductCarousel title="Mais Populares" products={popularProducts} />
      </main>

      <style>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
      `}</style>
    </div>
  );
}
