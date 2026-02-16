import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  X,
  Star,
  Loader2,
  ImagePlus,
  ArrowLeft,
  ArrowRight,
  Package,
  FileText,
  DollarSign,
  Tag,
  CheckCircle,
  Ruler,
  Trash2,
  Search,
  ShoppingBag,
} from "lucide-react";
import { productService } from "@/services/productService";
import { storageService, IMAGE_UPLOAD_LIMITS } from "@/services/storageService";
import { listingImageService } from "@/services/listingImageService";
import type {
  FilterOptionsResponse,
  MarketplaceListingImage,
  CreateListingRequest,
  UpdateListingRequest,
  FormData,
  PendingImage,
  ProductListItem,
} from "@/types/product";
import { INITIAL_FORMDATA } from "@/constants/brazilianStates";

const MAX_IMAGES = 10;

const TOTAL_STEPS = 7;

interface UploadedImageUrl {
  url: string;
  isPrimary: boolean;
  order: number;
}

interface DraftData {
  step: number;
  formData: FormData;
  uploadedImageUrls: UploadedImageUrl[];
}

export function ListingForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditMode = Boolean(id);

  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<FormData>(INITIAL_FORMDATA);
  const [filterOptions, setFilterOptions] =
    useState<FilterOptionsResponse | null>(null);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [uploadedImageUrls, setUploadedImageUrls] = useState<
    UploadedImageUrl[]
  >([]);
  const [existingImages, setExistingImages] = useState<
    MarketplaceListingImage[]
  >([]);
  const [productSearch, setProductSearch] = useState("");
  const [productResults, setProductResults] = useState<ProductListItem[]>([]);
  const [allProducts, setAllProducts] = useState<ProductListItem[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<ProductListItem | null>(null);
  const [searchingProducts, setSearchingProducts] = useState(false);
  const [searchAbortController, setSearchAbortController] = useState<AbortController | null>(null);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({
    current: 0,
    total: 0,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [hasDraft, setHasDraft] = useState(false);

  const draftKey = isEditMode ? `listing_draft_${id}` : "listing_draft";

  // Load draft from localStorage
  useEffect(() => {
    if (isEditMode) return; // No localStorage for edit mode

    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) {
        const draft: DraftData = JSON.parse(saved);
        setHasDraft(true);
        setCurrentStep(draft.step);
        setFormData(draft.formData);
        setUploadedImageUrls(draft.uploadedImageUrls || []);

        // Restore selectedProduct from draft if product ID exists
        if (draft.formData.product && allProducts.length > 0) {
          const product = allProducts.find(p => p.id === Number(draft.formData.product));
          if (product) {
            setSelectedProduct(product);
          }
        }
      }
    } catch (err) {
      console.error("Error loading draft:", err);
      localStorage.removeItem(draftKey);
    }
  }, [draftKey, isEditMode, allProducts]);

  // Save draft to localStorage
  const saveDraft = useCallback(() => {
    if (isEditMode) return; // No localStorage for edit mode

    try {
      const draft: DraftData = {
        step: currentStep,
        formData,
        uploadedImageUrls,
      };
      localStorage.setItem(draftKey, JSON.stringify(draft));
    } catch (err) {
      console.error("Error saving draft:", err);
    }
  }, [
    currentStep,
    formData,
    uploadedImageUrls,
    draftKey,
    isEditMode,
  ]);

  // Auto-save draft when data changes
  useEffect(() => {
    if (!isEditMode && currentStep > 0) {
      saveDraft();
    }
  }, [
    currentStep,
    formData,
    uploadedImageUrls,
    saveDraft,
    isEditMode,
  ]);

  // Discard draft
  const discardDraft = useCallback(() => {
    localStorage.removeItem(draftKey);
    setHasDraft(false);
    setCurrentStep(1);
    setFormData(INITIAL_FORMDATA);
    setUploadedImageUrls([]);
    setPendingImages([]);
    setErrors({});
  }, [draftKey]);

  // Load filter options and products
  useEffect(() => {
    async function loadOptions() {
      try {
        const [opts, products] = await Promise.all([
          productService.getFilterOptions(),
          productService.getProducts(),
        ]);
        setFilterOptions(opts);
        setAllProducts(products);
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
          title: listing.title || "",
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
        setSelectedProduct({
          id: listing.product.id,
          name: listing.product.name,
          slug: listing.product.slug,
          code: listing.product.code ?? null,
        });
        setExistingImages(listing.images);
        // In edit mode, start at step 2 (skip image upload)
        setCurrentStep(2);
      } catch (err) {
        console.error("Erro ao carregar anúncio:", err);
      } finally {
        setLoading(false);
      }
    }
    loadListing();
  }, [isEditMode, id]);

  // Cleanup: Revoke object URLs when component unmounts or pendingImages change
  useEffect(() => {
    return () => {
      pendingImages.forEach((img) => {
        URL.revokeObjectURL(img.previewUrl);
      });
    };
  }, [pendingImages]);

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

  // Product search handler with debounce
  const handleProductSearch = useCallback(
    (term: string) => {
      setProductSearch(term);

      if (!term.trim()) {
        setProductResults([]);
        setSearchingProducts(false);
        if (searchAbortController) {
          searchAbortController.abort();
          setSearchAbortController(null);
        }
        return;
      }

      // Cancel previous search
      if (searchAbortController) {
        searchAbortController.abort();
      }

      setSearchingProducts(true);

      // Debounce: wait 300ms before searching
      const timeoutId = setTimeout(async () => {
        const controller = new AbortController();
        setSearchAbortController(controller);

        try {
          const results = await productService.getProducts({ search: term.trim() });
          // Only update if this request wasn't aborted
          if (!controller.signal.aborted) {
            setProductResults(results);
          }
        } catch (err: any) {
          if (err.name !== 'AbortError' && err.name !== 'CanceledError') {
            console.error("Erro ao buscar produtos:", err);
          }
        } finally {
          if (!controller.signal.aborted) {
            setSearchingProducts(false);
          }
        }
      }, 300);

      return () => clearTimeout(timeoutId);
    },
    [searchAbortController],
  );

  const selectProduct = useCallback(
    (product: ProductListItem) => {
      setSelectedProduct(product);
      setFormData((prev) => ({ ...prev, product: String(product.id) }));
      setProductSearch("");
      setProductResults([]);
      if (errors.product) {
        setErrors((prev) => {
          const next = { ...prev };
          delete next.product;
          return next;
        });
      }
    },
    [errors.product],
  );

  const clearProduct = useCallback(() => {
    setSelectedProduct(null);
    setFormData((prev) => ({ ...prev, product: "" }));
  }, []);

  // Step-specific validation
  const validateStep = (step: number): boolean => {
    const newErrors: Record<string, string> = {};

    switch (step) {
      case 1: // Images - optional, no validation needed
        break;
      case 2: // Product
        if (!formData.product || formData.product.trim() === "" || Number(formData.product) <= 0) {
          newErrors.product = "Selecione um produto";
        }
        break;
      case 3: // Title
        if (!formData.title.trim())
          newErrors.title = "O título do anúncio é obrigatório";
        if (formData.title.length > 150)
          newErrors.title = "Máximo 150 caracteres";
        break;
      case 4: // Description
        if (!formData.description.trim())
          newErrors.description = "Descrição é obrigatória";
        if (formData.description.length > 255)
          newErrors.description = "Máximo 255 caracteres";
        break;
      case 5: // Price and Quantity
        if (!formData.price || Number(formData.price) <= 0)
          newErrors.price = "Preço inválido";
        break;
      case 6: // Brand and Condition
        if (!formData.brand) newErrors.brand = "Selecione uma marca";
        if (!formData.condition) newErrors.condition = "Selecione a condição";
        break;
      case 7: // Dimensions and Weight
        if (!formData.weight_kg || Number(formData.weight_kg) <= 0)
          newErrors.weight_kg = "Peso inválido";
        if (!formData.height_cm || Number(formData.height_cm) <= 0)
          newErrors.height_cm = "Altura inválida";
        if (!formData.width_cm || Number(formData.width_cm) <= 0)
          newErrors.width_cm = "Largura inválida";
        if (!formData.length_cm || Number(formData.length_cm) <= 0)
          newErrors.length_cm = "Comprimento inválido";
        break;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const [isDragging, setIsDragging] = useState(false);

  const processFiles = useCallback(
    (files: FileList | File[]): PendingImage[] => {
      const totalImages =
        pendingImages.length + existingImages.length + uploadedImageUrls.length;
      const remaining = MAX_IMAGES - totalImages;

      if (remaining <= 0) {
        setUploadError(`Máximo de ${MAX_IMAGES} imagens permitidas.`);
        return [];
      }

      const newImages: PendingImage[] = [];
      const filesToProcess = Array.from(files).slice(0, remaining);
      const errors: string[] = [];

      for (const file of filesToProcess) {
        if (
          !IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES.includes(
            file.type as (typeof IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES)[number],
          )
        ) {
          errors.push(
            `${file.name}: tipo não suportado. Use JPEG, PNG ou WebP.`,
          );
          continue;
        }
        if (file.size > IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES) {
          errors.push(
            `${file.name}: muito grande. Máximo ${IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB.`,
          );
          continue;
        }

        newImages.push({
          id: crypto.randomUUID(),
          file,
          previewUrl: URL.createObjectURL(file),
          isPrimary:
            totalImages === 0 &&
            newImages.length === 0 &&
            uploadedImageUrls.length === 0,
        });
      }

      if (errors.length > 0) {
        setUploadError(errors.join(" | "));
      } else {
        setUploadError(null);
      }

      return newImages;
    },
    [pendingImages.length, existingImages.length, uploadedImageUrls.length],
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;

      const newImages = processFiles(files);
      if (newImages.length > 0) {
        setPendingImages((prev) => [...prev, ...newImages]);
      }

      e.target.value = "";
    },
    [processFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);

      const files = e.dataTransfer.files;
      if (!files) return;

      const newImages = processFiles(files);
      if (newImages.length > 0) {
        setPendingImages((prev) => [...prev, ...newImages]);
      }
    },
    [processFiles],
  );

  const removePendingImage = useCallback(
    (imageId: string) => {
      setPendingImages((prev) => {
        const imageToRemove = prev.find((img) => img.id === imageId);
        if (imageToRemove) {
          URL.revokeObjectURL(imageToRemove.previewUrl);
        }

        const filtered = prev.filter((img) => img.id !== imageId);

        // If removed image was primary and there are others, make first one primary
        if (
          filtered.length > 0 &&
          !filtered.some((img) => img.isPrimary) &&
          existingImages.length === 0 &&
          uploadedImageUrls.length === 0
        ) {
          return filtered.map((img, index) =>
            index === 0 ? { ...img, isPrimary: true } : img,
          );
        }

        return filtered;
      });
    },
    [existingImages.length, uploadedImageUrls.length],
  );

  const setPendingPrimary = useCallback((imageId: string) => {
    setPendingImages((prev) =>
      prev.map((img) => ({ ...img, isPrimary: img.id === imageId })),
    );
    // Also unset existing images as primary (visually)
    setExistingImages((prev) =>
      prev.map((img) => ({ ...img, is_primary: false })),
    );
  }, []);

  // Upload images to S3 and save URLs (Step 1)
  const uploadImagesToS3 = useCallback(async () => {
    if (pendingImages.length === 0) return;

    setUploading(true);
    setUploadError(null);
    setUploadProgress({ current: 0, total: pendingImages.length });

    const newUploadedUrls: UploadedImageUrl[] = [];

    try {
      for (let i = 0; i < pendingImages.length; i++) {
        const img = pendingImages[i];
        setUploadProgress({ current: i + 1, total: pendingImages.length });

        // Step 1: Get presigned URL
        const { upload_url, file_url } = await storageService.getPresignedUrl(
          img.file.name,
          img.file.type,
        );

        // Step 2: Upload to S3
        await storageService.uploadToS3(upload_url, img.file);

        newUploadedUrls.push({
          url: file_url,
          isPrimary: img.isPrimary,
          order: uploadedImageUrls.length + i,
        });
      }

      // Save URLs and clear pending images
      setUploadedImageUrls((prev) => [...prev, ...newUploadedUrls]);
      setPendingImages((prev) => {
        prev.forEach((img) => URL.revokeObjectURL(img.previewUrl));
        return [];
      });
    } catch (err) {
      console.error("Erro ao fazer upload de imagens:", err);
      setUploadError(
        `Erro ao fazer upload de imagens. ${newUploadedUrls.length} de ${pendingImages.length} foram enviadas.`,
      );
      // Save partial uploads
      if (newUploadedUrls.length > 0) {
        setUploadedImageUrls((prev) => [...prev, ...newUploadedUrls]);
      }
      throw err;
    } finally {
      setUploading(false);
      setUploadProgress({ current: 0, total: 0 });
    }
  }, [pendingImages, uploadedImageUrls.length]);

  // Link uploaded images to listing (Final step)
  const linkImagesToListing = useCallback(
    async (listingId: number) => {
      if (uploadedImageUrls.length === 0) return;

      try {
        for (const img of uploadedImageUrls) {
          await listingImageService.addImage(listingId, {
            image_url: img.url,
            is_primary: img.isPrimary,
            order: img.order,
          });
        }
      } catch (err) {
        console.error("Erro ao vincular imagens ao anúncio:", err);
        throw new Error("Erro ao vincular imagens ao anúncio.");
      }
    },
    [uploadedImageUrls],
  );

  // Format decimal to 2 places (FIX for 400 Bad Request)
  const formatDecimal = (value: string): string => {
    const num = parseFloat(value);
    if (isNaN(num)) return "0.00";
    return num.toFixed(2);
  };

  const buildListingData = useCallback(() => {
    return {
      product: Number(formData.product),
      title: formData.title.trim(),
      brand: Number(formData.brand),
      condition: Number(formData.condition),
      description: formData.description.trim(),
      price: formatDecimal(formData.price),
      quantity: Number(formData.quantity) || 1,
      weight_kg: formatDecimal(formData.weight_kg),
      height_cm: formatDecimal(formData.height_cm),
      width_cm: formatDecimal(formData.width_cm),
      length_cm: formatDecimal(formData.length_cm),
    };
  }, [formData]);

  // Handle "Continuar" button (Step 1-5)
  const handleContinue = async () => {
    if (!validateStep(currentStep)) return;

    // Step 1: Upload images to S3 before proceeding
    if (currentStep === 1 && pendingImages.length > 0) {
      try {
        await uploadImagesToS3();
      } catch (err) {
        return; // Error already shown in uploadImagesToS3
      }
    }

    setCurrentStep((prev) => Math.min(prev + 1, TOTAL_STEPS));
    setErrors({});
  };

  // Handle "Voltar" button
  const handleBack = () => {
    // In edit mode, skip step 1
    if (isEditMode && currentStep === 2) {
      navigate(-1);
      return;
    }
    setCurrentStep((prev) => Math.max(prev - 1, 1));
    setErrors({});
  };

  // Handle final submit (Step 7 - "Publicar Anúncio")
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateStep(7)) return;

    setSubmitting(true);
    setUploadError(null);

    try {
      if (isEditMode && id) {
        // Edit mode: update listing first, then upload new images
        const updateData: UpdateListingRequest = buildListingData();
        await productService.updateListing(Number(id), updateData);

        // Upload new pending images if any
        if (pendingImages.length > 0) {
          try {
            await uploadImagesToS3();
            // Link new images
            for (const img of uploadedImageUrls) {
              await listingImageService.addImage(Number(id), {
                image_url: img.url,
                is_primary: img.isPrimary,
                order: img.order,
              });
            }
          } catch (uploadErr) {
            console.error("Upload error:", uploadErr);
            setUploadError(
              "Anúncio atualizado, mas houve erro ao enviar algumas imagens.",
            );
          }
        }

        navigate(`/productdetail/${id}`);
      } else {
        // Create mode: create listing FIRST, THEN link images
        const createData: CreateListingRequest = buildListingData();

        // Step 1: Create the listing
        const listing = await productService.createListing(createData);

        // Step 2: Link uploaded images to the created listing
        if (uploadedImageUrls.length > 0) {
          try {
            await linkImagesToListing(listing.id);
          } catch (linkErr) {
            console.error("Link error:", linkErr);
            setUploadError(
              "Anúncio criado, mas houve erro ao vincular algumas imagens. Você pode adicioná-las editando o anúncio.",
            );
            localStorage.removeItem(draftKey);
            setTimeout(() => navigate(`/productdetail/${listing.id}`), 3000);
            return;
          }
        }

        // Clear draft and navigate
        localStorage.removeItem(draftKey);
        navigate(`/productdetail/${listing.id}`);
      }
    } catch (err: any) {
      console.error("Erro ao salvar anúncio:", err);

      // FIX: Parse API field-level errors
      if (err.response?.data) {
        console.error("API validation errors:", err.response.data);
        const apiErrors = err.response.data;
        const newErrors: Record<string, string> = {};

        // Map API field errors to form errors
        Object.keys(apiErrors).forEach((field) => {
          const messages = apiErrors[field];
          if (Array.isArray(messages) && messages.length > 0) {
            newErrors[field] = messages[0];
          }
        });

        if (Object.keys(newErrors).length > 0) {
          setErrors(newErrors);
          setUploadError("Por favor, corrija os erros nos campos destacados.");
          return;
        }
      }

      const errorMessage =
        err.message || "Erro ao salvar anúncio. Tente novamente.";
      setUploadError(errorMessage);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-blue-900 flex items-center justify-center">
        <Loader2 size={48} className="text-white animate-spin" />
      </div>
    );
  }

  const totalImages =
    pendingImages.length + existingImages.length + uploadedImageUrls.length;

  // Step configuration
  const stepConfig = [
    { step: 1, title: "Imagens", icon: ImagePlus },
    { step: 2, title: "Produto", icon: ShoppingBag },
    { step: 3, title: "Título", icon: Package },
    { step: 4, title: "Descrição", icon: FileText },
    { step: 5, title: "Preço", icon: DollarSign },
    { step: 6, title: "Marca", icon: Tag },
    { step: 7, title: "Dimensões", icon: Ruler },
  ];

  return (
    <div className="min-h-screen bg-blue-900">
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-6 pb-24">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="p-2 text-white hover:bg-white/10 rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900"
            aria-label="Voltar"
          >
            <ArrowLeft size={24} />
          </button>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">
            {isEditMode ? "Editar Anúncio" : "Criar Anúncio"}
          </h1>
        </div>

        {/* Draft Notice */}
        {!isEditMode && hasDraft && currentStep === 1 && (
          <div className="bg-blue-800 rounded-xl p-4 mb-6 border border-blue-700">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-white font-medium mb-1">
                  Rascunho encontrado
                </p>
                <p className="text-blue-200 text-sm">
                  Você tem um rascunho salvo. Continue de onde parou ou descarte
                  para começar um novo anúncio.
                </p>
              </div>
              <button
                type="button"
                onClick={discardDraft}
                className="flex items-center gap-1 px-3 py-2 bg-white/10 text-white rounded-lg text-sm hover:bg-white/20 transition-all border border-white/20 whitespace-nowrap"
              >
                <Trash2 size={14} />
                Descartar
              </button>
            </div>
          </div>
        )}

        {/* Step Progress Indicator */}
        <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-900">
              Passo {currentStep} de {TOTAL_STEPS}
            </h2>
            <span className="text-xs text-gray-500">
              {Math.round((currentStep / TOTAL_STEPS) * 100)}% completo
            </span>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-gray-200 rounded-full h-2 mb-4">
            <div
              className="bg-blue-800 h-2 rounded-full transition-all duration-300"
              style={{ width: `${(currentStep / TOTAL_STEPS) * 100}%` }}
            />
          </div>

          {/* Step dots */}
          <div className="flex items-center justify-between">
            {stepConfig.map(({ step, title, icon: Icon }) => (
              <div key={step} className="flex flex-col items-center gap-2">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                    step < currentStep
                      ? "bg-green-500 text-white"
                      : step === currentStep
                        ? "bg-blue-800 text-white"
                        : "bg-gray-200 text-gray-400"
                  }`}
                >
                  {step < currentStep ? (
                    <CheckCircle size={20} />
                  ) : (
                    <Icon size={20} />
                  )}
                </div>
                <span
                  className={`text-[10px] sm:text-xs font-medium text-center ${
                    step === currentStep
                      ? "text-blue-800"
                      : step < currentStep
                        ? "text-green-600"
                        : "text-gray-400"
                  }`}
                >
                  {title}
                </span>
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* STEP 1: IMAGES */}
          {currentStep === 1 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                  <ImagePlus size={20} className="text-blue-800" />
                  Imagens do Produto
                </h2>
                <span className="text-sm font-medium text-gray-600 bg-gray-100 px-3 py-1 rounded-full">
                  {totalImages}/{MAX_IMAGES}
                </span>
              </div>

              {/* Uploaded images (from S3) */}
              {uploadedImageUrls.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                  {uploadedImageUrls.map((img, idx) => (
                    <div key={idx} className="relative group">
                      <div
                        className={`aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                          img.isPrimary
                            ? "border-yellow-400 ring-2 ring-yellow-200"
                            : "border-gray-200 hover:border-blue-800"
                        }`}
                      >
                        <img
                          src={img.url}
                          alt="Imagem enviada"
                          className="w-full h-full object-cover"
                        />
                      </div>
                      {img.isPrimary && (
                        <span className="absolute bottom-2 left-2 text-[10px] bg-yellow-400 text-yellow-900 px-2 py-1 rounded-md font-semibold shadow-sm">
                          Principal
                        </span>
                      )}
                      <span className="absolute top-1 left-1 text-[10px] bg-green-500 text-white px-2 py-1 rounded-md font-semibold shadow-sm">
                        Enviada
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Pending images */}
              {pendingImages.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                  {pendingImages.map((img) => (
                    <div key={img.id} className="relative group">
                      <div
                        className={`aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                          img.isPrimary
                            ? "border-yellow-400 ring-2 ring-yellow-200"
                            : "border-gray-200 hover:border-blue-800"
                        }`}
                      >
                        <img
                          src={img.previewUrl}
                          alt="Preview"
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          type="button"
                          onClick={() => setPendingPrimary(img.id)}
                          className={`p-2 rounded-full shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-1 ${
                            img.isPrimary
                              ? "bg-yellow-400 text-yellow-900"
                              : "bg-white text-gray-600 hover:text-yellow-600 hover:bg-yellow-50"
                          }`}
                          title="Definir como principal"
                          aria-label="Definir como principal"
                        >
                          <Star size={16} />
                        </button>
                        <button
                          type="button"
                          onClick={() => removePendingImage(img.id)}
                          className="p-2 bg-white text-red-500 rounded-full shadow-md hover:bg-red-50 transition-all focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-1"
                          title="Remover imagem"
                          aria-label="Remover imagem"
                        >
                          <X size={16} />
                        </button>
                      </div>
                      {img.isPrimary && (
                        <span className="absolute bottom-2 left-2 text-[10px] bg-yellow-400 text-yellow-900 px-2 py-1 rounded-md font-semibold shadow-sm">
                          Principal
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Upload button with drag-and-drop */}
              {totalImages < MAX_IMAGES && !uploading && (
                <label
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`flex flex-col items-center justify-center gap-2 p-8 border-2 border-dashed rounded-lg cursor-pointer transition-all ${
                    isDragging
                      ? "border-blue-800 bg-blue-50 scale-[1.02]"
                      : "border-gray-300 hover:border-blue-800 hover:bg-blue-50/50"
                  }`}
                >
                  <ImagePlus
                    size={40}
                    className={`transition-colors ${isDragging ? "text-blue-800" : "text-gray-400"}`}
                  />
                  <span className="text-sm text-gray-700 font-medium text-center">
                    {isDragging
                      ? "Solte as imagens aqui"
                      : "Clique ou arraste imagens para adicionar"}
                  </span>
                  <span className="text-xs text-gray-500 text-center">
                    JPEG, PNG ou WebP • Máximo 5MB por imagem
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

              {/* Upload progress */}
              {uploading && (
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center gap-3 mb-2">
                    <Loader2 size={20} className="text-blue-800 animate-spin" />
                    <p className="text-sm text-blue-800 font-medium">
                      Enviando imagens... {uploadProgress.current} de{" "}
                      {uploadProgress.total}
                    </p>
                  </div>
                  <div className="w-full bg-blue-200 rounded-full h-2">
                    <div
                      className="bg-blue-800 h-2 rounded-full transition-all"
                      style={{
                        width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              )}

              {uploadError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-start gap-2">
                    <X size={16} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-red-800">{uploadError}</p>
                  </div>
                </div>
              )}

              {totalImages === 0 && !uploading && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-xs text-blue-800">
                    <strong>Dica:</strong> Adicione pelo menos uma imagem para
                    tornar seu anúncio mais atrativo. A primeira imagem será a
                    principal.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* STEP 2: PRODUCT */}
          {currentStep === 2 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <ShoppingBag size={20} className="text-blue-800" />
                Produto
              </h2>
              <p className="text-sm text-gray-500">
                Selecione o produto que melhor se enquadra no seu anúncio.
              </p>

              {/* Selected product display */}
              {selectedProduct ? (
                <div className="flex items-center justify-between p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {selectedProduct.name}
                    </p>
                    {selectedProduct.code && (
                      <p className="text-xs text-gray-500">
                        Código: {selectedProduct.code}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={clearProduct}
                    className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                    aria-label="Remover produto"
                  >
                    <X size={18} />
                  </button>
                </div>
              ) : (
                <>
                  {/* Search input */}
                  <div className="relative">
                    <Search
                      className="absolute left-3 top-2.5 text-gray-400"
                      size={18}
                    />
                    <input
                      type="text"
                      value={productSearch}
                      onChange={(e) => handleProductSearch(e.target.value)}
                      placeholder="Buscar produto por nome..."
                      className={`w-full pl-10 pr-4 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                        errors.product
                          ? "border-red-300 bg-red-50"
                          : "border-gray-300 bg-white"
                      }`}
                    />
                    {searchingProducts && (
                      <Loader2
                        size={18}
                        className="absolute right-3 top-2.5 text-blue-800 animate-spin"
                      />
                    )}
                  </div>

                  {errors.product && (
                    <div className="flex items-start gap-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">{errors.product}</p>
                    </div>
                  )}

                  {/* Search results */}
                  {productSearch.trim() && productResults.length > 0 && (
                    <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto divide-y divide-gray-100">
                      {productResults.map((product) => (
                        <button
                          key={product.id}
                          type="button"
                          onClick={() => selectProduct(product)}
                          className="w-full text-left px-3 py-2.5 hover:bg-blue-50 transition-colors"
                        >
                          <p className="text-sm font-medium text-gray-900">
                            {product.name}
                          </p>
                          {product.code && (
                            <p className="text-xs text-gray-500">
                              Código: {product.code}
                            </p>
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {productSearch.trim() &&
                    !searchingProducts &&
                    productResults.length === 0 && (
                      <p className="text-sm text-gray-500 text-center py-2">
                        Nenhum produto encontrado.
                      </p>
                    )}

                  {/* Quick select from all products */}
                  {!productSearch.trim() && allProducts.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-2">
                        Ou selecione da lista:
                      </p>
                      <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto divide-y divide-gray-100">
                        {allProducts.map((product) => (
                          <button
                            key={product.id}
                            type="button"
                            onClick={() => selectProduct(product)}
                            className="w-full text-left px-3 py-2.5 hover:bg-blue-50 transition-colors"
                          >
                            <p className="text-sm font-medium text-gray-900">
                              {product.name}
                            </p>
                            {product.code && (
                              <p className="text-xs text-gray-500">
                                Código: {product.code}
                              </p>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* STEP 3: TITLE */}
          {currentStep === 3 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Package size={20} className="text-blue-800" />
                Título
              </h2>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Título do anúncio *
                </label>
                <input
                  type="text"
                  name="title"
                  value={formData.title}
                  onChange={handleChange}
                  maxLength={150}
                  placeholder="Ex: Esteira Elétrica Movement R3 Semi-Nova"
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.title
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                />
                <div className="flex justify-between items-center mt-1">
                  {errors.title ? (
                    <div className="flex items-start gap-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">{errors.title}</p>
                    </div>
                  ) : (
                    <span />
                  )}
                  <span
                    className={`text-xs ${formData.title.length > 130 ? "text-orange-500 font-medium" : "text-gray-400"}`}
                  >
                    {formData.title.length}/150
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: DESCRIPTION */}
          {currentStep === 4 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <FileText size={20} className="text-blue-800" />
                Descrição
              </h2>

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
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent resize-none transition-colors ${
                    errors.description
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                />
                <div className="flex justify-between items-center mt-1">
                  {errors.description ? (
                    <div className="flex items-start gap-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">
                        {errors.description}
                      </p>
                    </div>
                  ) : (
                    <span />
                  )}
                  <span
                    className={`text-xs ${formData.description.length > 240 ? "text-orange-500 font-medium" : "text-gray-400"}`}
                  >
                    {formData.description.length}/255
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* STEP 5: PRICE AND QUANTITY */}
          {currentStep === 5 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <DollarSign size={20} className="text-blue-800" />
                Preço e Quantidade
              </h2>

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
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.price
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                />
                {errors.price && (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.price}</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Quantidade disponível
                </label>
                <input
                  type="number"
                  name="quantity"
                  value={formData.quantity}
                  onChange={handleChange}
                  min="1"
                  max="2147483647"
                  placeholder="1"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent"
                />
                <p className="text-xs text-gray-500 mt-1">Padrão: 1 unidade</p>
              </div>
            </div>
          )}

          {/* STEP 6: BRAND AND CONDITION */}
          {currentStep === 6 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Tag size={20} className="text-blue-800" />
                Marca e Condição
              </h2>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Selecione a marca *
                </label>
                <select
                  name="brand"
                  value={formData.brand}
                  onChange={handleChange}
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.brand
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                >
                  <option value="">Selecione uma marca</option>
                  {filterOptions?.brands.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
                {errors.brand && (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.brand}</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Condição do produto *
                </label>
                <select
                  name="condition"
                  value={formData.condition}
                  onChange={handleChange}
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.condition
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                >
                  <option value="">Selecione a condição</option>
                  {filterOptions?.conditions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                {errors.condition && (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.condition}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 7: DIMENSIONS AND WEIGHT */}
          {currentStep === 7 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                  <Ruler size={20} className="text-blue-800" />
                  Dimensões e Peso
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Necessário para cálculo de frete
                </p>
              </div>

              {/* Weight */}
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
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.weight_kg
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                />
                {errors.weight_kg && (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.weight_kg}</p>
                  </div>
                )}
              </div>

              {/* Dimensions Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* Height */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Altura (cm) *
                  </label>
                  <input
                    type="number"
                    name="height_cm"
                    value={formData.height_cm}
                    onChange={handleChange}
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                      errors.height_cm
                        ? "border-red-300 bg-red-50"
                        : "border-gray-300 bg-white"
                    }`}
                  />
                  {errors.height_cm && (
                    <div className="flex items-start gap-1 mt-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">{errors.height_cm}</p>
                    </div>
                  )}
                </div>

                {/* Width */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Largura (cm) *
                  </label>
                  <input
                    type="number"
                    name="width_cm"
                    value={formData.width_cm}
                    onChange={handleChange}
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                      errors.width_cm
                        ? "border-red-300 bg-red-50"
                        : "border-gray-300 bg-white"
                    }`}
                  />
                  {errors.width_cm && (
                    <div className="flex items-start gap-1 mt-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">{errors.width_cm}</p>
                    </div>
                  )}
                </div>

                {/* Length */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Comprimento (cm) *
                  </label>
                  <input
                    type="number"
                    name="length_cm"
                    value={formData.length_cm}
                    onChange={handleChange}
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                      errors.length_cm
                        ? "border-red-300 bg-red-50"
                        : "border-gray-300 bg-white"
                    }`}
                  />
                  {errors.length_cm && (
                    <div className="flex items-start gap-1 mt-1">
                      <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-red-600 text-xs">{errors.length_cm}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Global Upload Error */}
          {uploadError && currentStep > 1 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <div className="flex items-start gap-2">
                <X size={16} className="text-red-500 shrink-0 mt-0.5" />
                <p className="text-xs text-red-800">{uploadError}</p>
              </div>
            </div>
          )}

          {/* Navigation Buttons */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            {currentStep > 1 && (
              <button
                type="button"
                onClick={handleBack}
                disabled={submitting || uploading}
                className="w-full sm:flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white/10 text-white border border-white/20 rounded-lg font-semibold hover:bg-white/20 transition-all focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ArrowLeft size={20} />
                Voltar
              </button>
            )}

            {currentStep < TOTAL_STEPS ? (
              <button
                type="button"
                onClick={handleContinue}
                disabled={uploading}
                className="w-full sm:flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white text-blue-900 rounded-lg font-semibold hover:bg-gray-100 transition-all shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-md"
              >
                {uploading ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    Enviando imagens...
                  </>
                ) : (
                  <>
                    Continuar
                    <ArrowRight size={20} />
                  </>
                )}
              </button>
            ) : (
              <button
                type="submit"
                disabled={submitting}
                className="w-full sm:flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white text-blue-900 rounded-lg font-semibold hover:bg-gray-100 transition-all shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-md"
              >
                {submitting ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    {isEditMode ? "Salvando..." : "Publicando..."}
                  </>
                ) : (
                  <>
                    <CheckCircle size={20} />
                    {isEditMode ? "Salvar Alterações" : "Publicar Anúncio"}
                  </>
                )}
              </button>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
