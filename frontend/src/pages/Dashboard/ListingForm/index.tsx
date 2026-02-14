import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { X, Star, Loader2, ImagePlus, Save, ArrowLeft } from "lucide-react";
import { productService } from "@/services/productService";
import { storageService } from "@/services/storageService";
import { listingImageService } from "@/services/listingImageService";
import type {
  ProductListItem,
  FilterOptionsResponse,
  MarketplaceListingImage,
  CreateListingRequest,
  UpdateListingRequest,
  FormData,
  PendingImage,
} from "@/types/product";
import { INITIAL_FORMDATA } from "@/constants/brazilianStates";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB
const MAX_IMAGES = 10;

export function ListingForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditMode = Boolean(id);

  const [formData, setFormData] = useState<FormData>(INITIAL_FORMDATA);
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [filterOptions, setFilterOptions] =
    useState<FilterOptionsResponse | null>(null);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [existingImages, setExistingImages] = useState<
    MarketplaceListingImage[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [productSearch, setProductSearch] = useState("");

  // Load filter options and products
  useEffect(() => {
    async function loadOptions() {
      try {
        const [opts, prods] = await Promise.all([
          productService.getFilterOptions(),
          productService.getProducts(),
        ]);
        setFilterOptions(opts);
        setProducts(prods);
      } catch (err) {
        console.error("Erro ao carregar opções:", err);
      } finally {
        if (!isEditMode) setLoading(false);
      }
    }
    loadOptions();
  }, [isEditMode]);

  // Load existing listing data in edit mode
  useEffect(() => {
    if (!isEditMode || !id) return;

    async function loadListing() {
      try {
        const listing = await productService.getListingById(Number(id));
        setFormData({
          product: String(listing.product.id),
          brand: String(listing.brand.id),
          condition: String(listing.condition.id),
          description: listing.description,
          price: listing.price,
          quantity: String(listing.quantity),
          weight_kg: listing.weight_kg || "",
          height_cm: listing.height_cm || "",
          width_cm: listing.width_cm || "",
          length_cm: listing.length_cm || "",
        });
        setExistingImages(listing.images);
      } catch (err) {
        console.error("Erro ao carregar anúncio:", err);
      } finally {
        setLoading(false);
      }
    }
    loadListing();
  }, [isEditMode, id]);

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.product) newErrors.product = "Selecione um produto";
    if (!formData.brand) newErrors.brand = "Selecione uma marca";
    if (!formData.condition) newErrors.condition = "Selecione a condição";
    if (!formData.description.trim())
      newErrors.description = "Descrição é obrigatória";
    if (formData.description.length > 255)
      newErrors.description = "Máximo 255 caracteres";
    if (!formData.price || Number(formData.price) <= 0)
      newErrors.price = "Preço inválido";
    if (!formData.weight_kg || Number(formData.weight_kg) <= 0)
      newErrors.weight_kg = "Peso inválido";
    if (!formData.height_cm || Number(formData.height_cm) <= 0)
      newErrors.height_cm = "Altura inválida";
    if (!formData.width_cm || Number(formData.width_cm) <= 0)
      newErrors.width_cm = "Largura inválida";
    if (!formData.length_cm || Number(formData.length_cm) <= 0)
      newErrors.length_cm = "Comprimento inválido";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;

      const totalImages = pendingImages.length + existingImages.length;
      const remaining = MAX_IMAGES - totalImages;
      if (remaining <= 0) {
        alert(`Máximo de ${MAX_IMAGES} imagens permitidas.`);
        return;
      }

      const newImages: PendingImage[] = [];
      const filesToProcess = Array.from(files).slice(0, remaining);

      for (const file of filesToProcess) {
        if (!ACCEPTED_TYPES.includes(file.type)) {
          alert(`Tipo não suportado: ${file.name}. Use JPEG, PNG ou WebP.`);
          continue;
        }
        if (file.size > MAX_FILE_SIZE) {
          alert(`Arquivo muito grande: ${file.name}. Máximo 5MB.`);
          continue;
        }

        newImages.push({
          id: crypto.randomUUID(),
          file,
          previewUrl: URL.createObjectURL(file),
          isPrimary: totalImages === 0 && newImages.length === 0,
        });
      }

      setPendingImages((prev) => [...prev, ...newImages]);
      e.target.value = "";
    },
    [pendingImages.length, existingImages.length],
  );

  const removePendingImage = (imageId: string) => {
    setPendingImages((prev) => {
      const filtered = prev.filter((img) => img.id !== imageId);
      // If removed image was primary and there are others, make first one primary
      if (
        filtered.length > 0 &&
        !filtered.some((img) => img.isPrimary) &&
        existingImages.length === 0
      ) {
        filtered[0].isPrimary = true;
      }
      return filtered;
    });
  };

  const removeExistingImage = async (imageId: number) => {
    if (!id) return;
    try {
      await listingImageService.deleteImage(Number(id), imageId);
      setExistingImages((prev) => prev.filter((img) => img.id !== imageId));
    } catch (err) {
      console.error("Erro ao remover imagem:", err);
      alert("Erro ao remover imagem.");
    }
  };

  const setPendingPrimary = (imageId: string) => {
    setPendingImages((prev) =>
      prev.map((img) => ({ ...img, isPrimary: img.id === imageId })),
    );
    // Also unset existing images as primary (visually)
    setExistingImages((prev) =>
      prev.map((img) => ({ ...img, is_primary: false })),
    );
  };

  const setExistingPrimary = async (imageId: number) => {
    if (!id) return;
    try {
      await listingImageService.setPrimary(Number(id), imageId);
      setExistingImages((prev) =>
        prev.map((img) => ({ ...img, is_primary: img.id === imageId })),
      );
      setPendingImages((prev) =>
        prev.map((img) => ({ ...img, isPrimary: false })),
      );
    } catch (err) {
      console.error("Erro ao definir imagem principal:", err);
    }
  };

  const uploadImages = async (listingId: number) => {
    for (const img of pendingImages) {
      try {
        const { upload_url, file_url } = await storageService.getPresignedUrl(
          img.file.name,
          img.file.type,
        );
        await storageService.uploadToS3(upload_url, img.file);
        await listingImageService.addImage(listingId, {
          image_url: file_url,
          is_primary: img.isPrimary,
        });
      } catch (err) {
        console.error(`Erro ao fazer upload de ${img.file.name}:`, err);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    try {
      if (isEditMode && id) {
        const updateData: UpdateListingRequest = {
          product: Number(formData.product),
          brand: Number(formData.brand),
          condition: Number(formData.condition),
          description: formData.description.trim(),
          price: formData.price,
          quantity: Number(formData.quantity) || 1,
          weight_kg: formData.weight_kg,
          height_cm: formData.height_cm,
          width_cm: formData.width_cm,
          length_cm: formData.length_cm,
        };
        await productService.updateListing(Number(id), updateData);
        if (pendingImages.length > 0) {
          await uploadImages(Number(id));
        }
        navigate(`/productdetail/${id}`);
      } else {
        const createData: CreateListingRequest = {
          product: Number(formData.product),
          brand: Number(formData.brand),
          condition: Number(formData.condition),
          description: formData.description.trim(),
          price: formData.price,
          quantity: Number(formData.quantity) || 1,
          weight_kg: formData.weight_kg,
          height_cm: formData.height_cm,
          width_cm: formData.width_cm,
          length_cm: formData.length_cm,
        };
        const listing = await productService.createListing(createData);
        if (pendingImages.length > 0) {
          await uploadImages(listing.id);
        }
        navigate(`/productdetail/${listing.id}`);
      }
    } catch (err) {
      console.error("Erro ao salvar anúncio:", err);
      alert("Erro ao salvar anúncio. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  };

  const filteredProducts = productSearch
    ? products.filter((p) =>
        p.name.toLowerCase().includes(productSearch.toLowerCase()),
      )
    : products;

  if (loading) {
    return (
      <div className="min-h-screen bg-blue-900 flex items-center justify-center">
        <Loader2 size={48} className="text-white animate-spin" />
      </div>
    );
  }

  const totalImages = pendingImages.length + existingImages.length;

  return (
    <div className="min-h-screen bg-blue-900">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-6 pb-24">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="p-2 text-white hover:bg-white/10 rounded-lg transition"
          >
            <ArrowLeft size={24} />
          </button>
          <h1 className="text-2xl font-bold text-white">
            {isEditMode ? "Editar Anúncio" : "Criar Anúncio"}
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Product selection */}
          <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Produto</h2>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Buscar produto
              </label>
              <input
                type="text"
                value={productSearch}
                onChange={(e) => setProductSearch(e.target.value)}
                placeholder="Digite para buscar..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Produto *
              </label>
              <select
                name="product"
                value={formData.product}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
              >
                <option value="">Selecione um produto</option>
                {filteredProducts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.code ? `(${p.code})` : ""}
                  </option>
                ))}
              </select>
              {errors.product && (
                <p className="text-red-500 text-xs mt-1">{errors.product}</p>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Marca *
                </label>
                <select
                  name="brand"
                  value={formData.brand}
                  onChange={handleChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                >
                  <option value="">Selecione</option>
                  {filterOptions?.brands.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
                {errors.brand && (
                  <p className="text-red-500 text-xs mt-1">{errors.brand}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Condição *
                </label>
                <select
                  name="condition"
                  value={formData.condition}
                  onChange={handleChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                >
                  <option value="">Selecione</option>
                  {filterOptions?.conditions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                {errors.condition && (
                  <p className="text-red-500 text-xs mt-1">
                    {errors.condition}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Description */}
          <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Descrição</h2>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Descrição do anúncio *
              </label>
              <textarea
                name="description"
                value={formData.description}
                onChange={handleChange}
                maxLength={255}
                rows={4}
                placeholder="Descreva o produto, estado de conservação, acessórios inclusos..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent resize-none"
              />
              <div className="flex justify-between items-center mt-1">
                {errors.description ? (
                  <p className="text-red-500 text-xs">{errors.description}</p>
                ) : (
                  <span />
                )}
                <span className="text-xs text-gray-400">
                  {formData.description.length}/255
                </span>
              </div>
            </div>
          </div>

          {/* Price and quantity */}
          <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Preço e Quantidade
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Preço (R$) *
                </label>
                <input
                  type="number"
                  name="price"
                  value={formData.price}
                  onChange={handleChange}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                {errors.price && (
                  <p className="text-red-500 text-xs mt-1">{errors.price}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Quantidade
                </label>
                <input
                  type="number"
                  name="quantity"
                  value={formData.quantity}
                  onChange={handleChange}
                  min="1"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
              </div>
            </div>
          </div>

          {/* Dimensions */}
          <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Dimensões e Peso
            </h2>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Peso (kg) *
                </label>
                <input
                  type="number"
                  name="weight_kg"
                  value={formData.weight_kg}
                  onChange={handleChange}
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                {errors.weight_kg && (
                  <p className="text-red-500 text-xs mt-1">
                    {errors.weight_kg}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Altura (cm) *
                </label>
                <input
                  type="number"
                  name="height_cm"
                  value={formData.height_cm}
                  onChange={handleChange}
                  step="0.1"
                  min="0"
                  placeholder="0.0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                {errors.height_cm && (
                  <p className="text-red-500 text-xs mt-1">
                    {errors.height_cm}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Largura (cm) *
                </label>
                <input
                  type="number"
                  name="width_cm"
                  value={formData.width_cm}
                  onChange={handleChange}
                  step="0.1"
                  min="0"
                  placeholder="0.0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                {errors.width_cm && (
                  <p className="text-red-500 text-xs mt-1">{errors.width_cm}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Comp. (cm) *
                </label>
                <input
                  type="number"
                  name="length_cm"
                  value={formData.length_cm}
                  onChange={handleChange}
                  step="0.1"
                  min="0"
                  placeholder="0.0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                {errors.length_cm && (
                  <p className="text-red-500 text-xs mt-1">
                    {errors.length_cm}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Images */}
          <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Imagens</h2>
              <span className="text-sm text-gray-500">
                {totalImages}/{MAX_IMAGES}
              </span>
            </div>

            {/* Existing images (edit mode) */}
            {existingImages.length > 0 && (
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
                {existingImages.map((img) => (
                  <div key={img.id} className="relative group">
                    <div
                      className={`aspect-square rounded-lg overflow-hidden border-2 ${
                        img.is_primary ? "border-yellow-400" : "border-gray-200"
                      }`}
                    >
                      <img
                        src={img.image_url}
                        alt="Imagem do anúncio"
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition">
                      <button
                        type="button"
                        onClick={() => setExistingPrimary(img.id)}
                        className={`p-1 rounded-full shadow ${
                          img.is_primary
                            ? "bg-yellow-400 text-yellow-900"
                            : "bg-white text-gray-600 hover:text-yellow-600"
                        }`}
                        title="Definir como principal"
                      >
                        <Star size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeExistingImage(img.id)}
                        className="p-1 bg-white text-red-500 rounded-full shadow hover:bg-red-50"
                        title="Remover"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    {img.is_primary && (
                      <span className="absolute bottom-1 left-1 text-[10px] bg-yellow-400 text-yellow-900 px-1.5 py-0.5 rounded font-medium">
                        Principal
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Pending images */}
            {pendingImages.length > 0 && (
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
                {pendingImages.map((img) => (
                  <div key={img.id} className="relative group">
                    <div
                      className={`aspect-square rounded-lg overflow-hidden border-2 ${
                        img.isPrimary ? "border-yellow-400" : "border-gray-200"
                      }`}
                    >
                      <img
                        src={img.previewUrl}
                        alt="Preview"
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition">
                      <button
                        type="button"
                        onClick={() => setPendingPrimary(img.id)}
                        className={`p-1 rounded-full shadow ${
                          img.isPrimary
                            ? "bg-yellow-400 text-yellow-900"
                            : "bg-white text-gray-600 hover:text-yellow-600"
                        }`}
                        title="Definir como principal"
                      >
                        <Star size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removePendingImage(img.id)}
                        className="p-1 bg-white text-red-500 rounded-full shadow hover:bg-red-50"
                        title="Remover"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    {img.isPrimary && (
                      <span className="absolute bottom-1 left-1 text-[10px] bg-yellow-400 text-yellow-900 px-1.5 py-0.5 rounded font-medium">
                        Principal
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Upload button */}
            {totalImages < MAX_IMAGES && (
              <label className="flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:border-blue-800 hover:bg-blue-50/50 transition">
                <ImagePlus size={32} className="text-gray-400" />
                <span className="text-sm text-gray-500">
                  Clique para adicionar imagens
                </span>
                <span className="text-xs text-gray-400">
                  JPEG, PNG ou WebP. Máx 5MB cada.
                </span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </label>
            )}
          </div>

          {/* Submit */}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="flex-1 px-4 py-3 bg-white/10 text-white border border-white/20 rounded-lg font-semibold hover:bg-white/20 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white text-blue-900 rounded-lg font-semibold hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <Save size={20} />
              )}
              {isEditMode ? "Salvar Alterações" : "Publicar Anúncio"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
