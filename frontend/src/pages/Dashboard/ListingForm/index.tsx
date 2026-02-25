import { useState, useEffect, useCallback, useRef } from "react";
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
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { productService } from "@/services/productService";
import { storageService, IMAGE_UPLOAD_LIMITS } from "@/services/storageService";
import { listingImageService } from "@/services/listingImageService";
import { logisticsService } from "@/services/logisticsService";
import type {
  FilterOptionsResponse,
  MarketplaceListingImage,
  UpdateListingRequest,
  FormData,
  PendingImage,
  ProductListItem,
} from "@/types/product";
import { INITIAL_FORMDATA } from "@/constants/brazilianStates";
import {
  validateStep as validateStepHelper,
  formatDecimal,
  buildListingData as buildListingDataHelper,
} from "@/utils/listingHelpers";
import Swal from "sweetalert2";

const MAX_IMAGES = 10;

const TOTAL_STEPS = 7;

/**
 * Steps:
 * 1 - Produto
 * 2 - Título
 * 3 - Descrição
 * 4 - Marca & Condição
 * 5 - Preço & Quantidade
 * 6 - Dimensões do Pacote
 * 7 - Imagens
 */

const FIELD_TO_STEP: Record<string, number> = {
  product: 1,
  title: 2,
  brand: 4,
  condition: 4,
  description: 3,
  price: 5,
  quantity: 5,
  weight_kg: 6,
  height_cm: 6,
  width_cm: 6,
  length_cm: 6,
};

const STEP_NAMES: Record<number, string> = {
  1: "Produto",
  2: "Título",
  3: "Descrição",
  4: "Marca e Condição",
  5: "Preço",
  6: "Dimensões",
  7: "Imagens",
};

const STEP_ICONS: Record<number, React.ElementType> = {
  1: ShoppingBag,
  2: FileText,
  3: FileText,
  4: Tag,
  5: DollarSign,
  6: Ruler,
  7: ImagePlus,
};

interface UploadedImageUrl {
  url: string;
  objectName: string;
  isPrimary: boolean;
  order: number;
}

interface DraftData {
  step: number;
  formData: FormData;
}

export function ListingForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditMode = Boolean(id);

  // Melhor Envio gate
  const [meCheckLoading, setMeCheckLoading] = useState(true);
  const [meConnected, setMeConnected] = useState(false);
  const [meConnectUrl, setMeConnectUrl] = useState<string | null>(null);
  const [meCheckError, setMeCheckError] = useState(false);

  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<FormData>(INITIAL_FORMDATA);
  const [filterOptions, setFilterOptions] =
    useState<FilterOptionsResponse | null>(null);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [existingImages, setExistingImages] = useState<
    MarketplaceListingImage[]
  >([]);
  const [productSearch, setProductSearch] = useState("");
  const [productResults, setProductResults] = useState<ProductListItem[]>([]);
  const [allProducts, setAllProducts] = useState<ProductListItem[]>([]);
  const [productsPage, setProductsPage] = useState(1);
  const [hasMoreProducts, setHasMoreProducts] = useState(false);
  const [loadingMoreProducts, setLoadingMoreProducts] = useState(false);
  const [selectedProduct, setSelectedProduct] =
    useState<ProductListItem | null>(null);
  const [searchingProducts, setSearchingProducts] = useState(false);
  const [searchAbortController, setSearchAbortController] =
    useState<AbortController | null>(null);
  const draftProductRestoredRef = useRef(false);

  // Draft timing refs
  const draftStepRef = useRef<number>(1);
  const draftJustLoadedRef = useRef(false);

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
  const [isDragging, setIsDragging] = useState(false);

  const draftKey = isEditMode ? `listing_draft_${id}` : "listing_draft";

  // ============================================
  // MELHOR ENVIO GATE CHECK
  // ============================================
  useEffect(() => {
    async function checkMelhorEnvioConnection() {
      setMeCheckLoading(true);
      setMeCheckError(false);
      try {
        const status = await logisticsService.getMelhorEnvioStatus();
        if (status.connected && !status.is_expired) {
          setMeConnected(true);
        } else {
          setMeConnected(false);
          // Get the OAuth URL so we can show a direct connect button
          try {
            const connectData = await logisticsService.getMelhorEnvioConnectUrl();
            setMeConnectUrl(connectData.authorization_url);
          } catch {
            // URL fetch failure is non-fatal; user can still try
          }
        }
      } catch (err) {
        console.error("Erro ao verificar conexão Melhor Envio:", err);
        setMeCheckError(true);
      } finally {
        setMeCheckLoading(false);
      }
    }
    checkMelhorEnvioConnection();
  }, []);

  // ============================================
  // DRAFT MANAGEMENT
  // ============================================

  useEffect(() => {
    if (isEditMode) return;

    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) {
        const draft: DraftData = JSON.parse(saved);
        draftStepRef.current = draft.step ?? 1;
        draftJustLoadedRef.current = true;
        setHasDraft(true);
        setFormData(draft.formData);
      }
    } catch (err) {
      console.error("Error loading draft:", err);
      localStorage.removeItem(draftKey);
    }
  }, [draftKey, isEditMode]);

  // Restore selectedProduct from draft once allProducts loads
  useEffect(() => {
    if (
      isEditMode ||
      draftProductRestoredRef.current ||
      allProducts.length === 0
    )
      return;

    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) {
        const draft: DraftData = JSON.parse(saved);
        if (draft.formData.product) {
          const product = allProducts.find(
            (p) => p.id === Number(draft.formData.product),
          );
          if (product) {
            setSelectedProduct(product);
          }
          draftProductRestoredRef.current = true;
        }
      }
    } catch {
      // Already handled above
    }
  }, [allProducts, draftKey, isEditMode]);

  const saveDraft = useCallback(() => {
    if (isEditMode) return;

    try {
      const draft: DraftData = {
        step: currentStep,
        formData,
      };
      localStorage.setItem(draftKey, JSON.stringify(draft));
    } catch (err) {
      console.error("Error saving draft:", err);
    }
  }, [currentStep, formData, draftKey, isEditMode]);

  useEffect(() => {
    if (!isEditMode && currentStep > 0 && !draftJustLoadedRef.current) {
      saveDraft();
    }
  }, [currentStep, formData, saveDraft, isEditMode]);

  const discardDraft = useCallback(async () => {
    const result = await Swal.fire({
      title: "Descartar rascunho?",
      text: "Todos os dados preenchidos serão perdidos.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#1e3a8a",
      cancelButtonColor: "#6b7280",
      confirmButtonText: "Sim, descartar",
      cancelButtonText: "Cancelar",
    });

    if (!result.isConfirmed) return;

    draftJustLoadedRef.current = false;
    localStorage.removeItem(draftKey);
    setHasDraft(false);
    setCurrentStep(1);
    setFormData(INITIAL_FORMDATA);
    setPendingImages([]);
    setErrors({});
  }, [draftKey]);

  // ============================================
  // DATA LOADING
  // ============================================

  useEffect(() => {
    async function loadOptions() {
      try {
        const [opts, productsResponse] = await Promise.all([
          productService.getFilterOptions(),
          productService.getProducts(),
        ]);
        setFilterOptions(opts);
        setAllProducts(productsResponse.results);
        setHasMoreProducts(productsResponse.next !== null);
        setProductsPage(1);
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
        // Populate from first package if available
        const firstPkg =
          (listing as any).packages?.[0] ?? listing;
        setFormData({
          product: String(listing.product.id),
          title: listing.title || "",
          brand: String(listing.brand.id),
          condition: String(listing.condition.id),
          description: listing.description,
          price: listing.price,
          quantity: String(listing.quantity),
          weight_kg: firstPkg.weight_kg || "",
          height_cm: firstPkg.height_cm || "",
          width_cm: firstPkg.width_cm || "",
          length_cm: firstPkg.length_cm || "",
          package_description: firstPkg.description || "",
        });
        setSelectedProduct({
          id: listing.product.id,
          name: listing.product.name,
          slug: listing.product.slug,
          code: listing.product.code ?? null,
        });
        setExistingImages(listing.images);
        setCurrentStep(1);
      } catch (err) {
        console.error("Erro ao carregar anúncio:", err);
      } finally {
        setLoading(false);
      }
    }
    loadListing();
  }, [isEditMode, id]);

  // Cleanup pending image object URLs on unmount
  const pendingImagesRef = useRef(pendingImages);
  pendingImagesRef.current = pendingImages;

  useEffect(() => {
    return () => {
      pendingImagesRef.current.forEach((img) => {
        URL.revokeObjectURL(img.previewUrl);
      });
    };
  }, []);

  // ============================================
  // FORM HANDLERS
  // ============================================

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

      if (searchAbortController) {
        searchAbortController.abort();
      }

      setSearchingProducts(true);

      const timeoutId = setTimeout(async () => {
        const controller = new AbortController();
        setSearchAbortController(controller);

        try {
          const response = await productService.getProducts({
            search: term.trim(),
          });
          if (!controller.signal.aborted) {
            setProductResults(response.results);
          }
        } catch (err: any) {
          if (err.name !== "AbortError" && err.name !== "CanceledError") {
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

  const loadMoreProducts = useCallback(async () => {
    if (loadingMoreProducts || !hasMoreProducts) return;

    setLoadingMoreProducts(true);
    try {
      const nextPage = productsPage + 1;
      const response = await productService.getProducts({ page: nextPage });
      setAllProducts((prev) => [...prev, ...response.results]);
      setHasMoreProducts(response.next !== null);
      setProductsPage(nextPage);
    } catch (err) {
      console.error("Erro ao carregar mais produtos:", err);
    } finally {
      setLoadingMoreProducts(false);
    }
  }, [loadingMoreProducts, hasMoreProducts, productsPage]);

  const validateCurrentStep = (step: number): boolean => {
    const newErrors = validateStepHelper(step, formData);
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // ============================================
  // IMAGE HANDLERS
  // ============================================

  const processFiles = useCallback(
    (files: FileList | File[]): PendingImage[] => {
      const totalImages = pendingImages.length + existingImages.length;
      const remaining = MAX_IMAGES - totalImages;

      if (remaining <= 0) {
        setUploadError(`Máximo de ${MAX_IMAGES} imagens permitidas.`);
        return [];
      }

      const newImages: PendingImage[] = [];
      const filesToProcess = Array.from(files).slice(0, remaining);
      const fileErrors: string[] = [];

      for (const file of filesToProcess) {
        if (
          !IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES.includes(
            file.type as (typeof IMAGE_UPLOAD_LIMITS.ACCEPTED_TYPES)[number],
          )
        ) {
          fileErrors.push(
            `${file.name}: tipo não suportado. Use JPEG, PNG ou WebP.`,
          );
          continue;
        }
        if (file.size > IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES) {
          fileErrors.push(
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
            newImages.length === 0,
        });
      }

      if (fileErrors.length > 0) {
        setUploadError(fileErrors.join(" | "));
      } else {
        setUploadError(null);
      }

      return newImages;
    },
    [pendingImages.length, existingImages.length],
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

        if (
          filtered.length > 0 &&
          !filtered.some((img) => img.isPrimary) &&
          existingImages.length === 0
        ) {
          return filtered.map((img, index) =>
            index === 0 ? { ...img, isPrimary: true } : img,
          );
        }

        return filtered;
      });
    },
    [existingImages.length],
  );

  const setPendingPrimary = useCallback((imageId: string) => {
    setPendingImages((prev) =>
      prev.map((img) => ({ ...img, isPrimary: img.id === imageId })),
    );
    setExistingImages((prev) =>
      prev.map((img) => ({ ...img, is_primary: false })),
    );
  }, []);

  // ============================================
  // UPLOAD & LINK IMAGES
  // ============================================

  /**
   * Uploads pending images to S3 sequentially:
   * 1. Get presigned URL from backend
   * 2. PUT file to S3
   * Returns the list of uploaded URL objects.
   */
  const uploadImagesToS3 = useCallback(
    async (): Promise<UploadedImageUrl[]> => {
      if (pendingImages.length === 0) return [];

      setUploading(true);
      setUploadError(null);
      setUploadProgress({ current: 0, total: pendingImages.length });

      const newUploadedUrls: UploadedImageUrl[] = [];

      try {
        for (let i = 0; i < pendingImages.length; i++) {
          const img = pendingImages[i];
          setUploadProgress({ current: i + 1, total: pendingImages.length });

          const { upload_url, file_url, object_name } =
            await storageService.getPresignedUrl(img.file.name, img.file.type);

          await storageService.uploadToS3(upload_url, img.file);

          newUploadedUrls.push({
            url: file_url,
            objectName: object_name,
            isPrimary: img.isPrimary,
            order: i,
          });
        }

        setPendingImages((prev) => {
          prev.forEach((img) => URL.revokeObjectURL(img.previewUrl));
          return [];
        });

        return newUploadedUrls;
      } catch (err) {
        console.error("Erro ao fazer upload de imagens:", err);
        setUploadError(
          `Erro ao fazer upload de imagens. ${newUploadedUrls.length} de ${pendingImages.length} foram enviadas.`,
        );
        throw err;
      } finally {
        setUploading(false);
        setUploadProgress({ current: 0, total: 0 });
      }
    },
    [pendingImages],
  );

  /**
   * Links uploaded image URLs to an existing listing sequentially.
   */
  const linkImagesToListing = useCallback(
    async (listingId: number, uploadedUrls: UploadedImageUrl[]) => {
      for (const img of uploadedUrls) {
        await listingImageService.addImage(listingId, {
          image_url: img.url,
          object_name: img.objectName,
          is_primary: img.isPrimary,
          order: img.order,
        });
      }
    },
    [],
  );

  const buildListingData = useCallback(
    () => buildListingDataHelper(formData),
    [formData],
  );

  // ============================================
  // NAVIGATION
  // ============================================

  const handleContinue = async () => {
    if (!validateCurrentStep(currentStep)) return;

    setCurrentStep((prev) => Math.min(prev + 1, TOTAL_STEPS));
    setErrors({});
    setUploadError(null);
  };

  const handleBack = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 1));
    setErrors({});
    setUploadError(null);
  };

  // ============================================
  // SUBMIT
  // ============================================

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Only allow submission on last step
    if (currentStep < TOTAL_STEPS) {
      handleContinue();
      return;
    }

    // Validate all metadata steps (1-6) before submitting
    const allErrors: Record<string, string> = {};
    for (let step = 1; step <= 6; step++) {
      const stepErrors = validateStepHelper(step, formData);
      Object.assign(allErrors, stepErrors);
    }
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      const targetStep = Object.keys(allErrors).reduce((lowest, field) => {
        const step = FIELD_TO_STEP[field] ?? 1;
        return step < lowest ? step : lowest;
      }, 6);
      setCurrentStep(targetStep);
      return;
    }

    setSubmitting(true);
    setUploadError(null);

    try {
      if (isEditMode && id) {
        // Edit mode: update listing
        const updateData: UpdateListingRequest = {
          ...buildListingData(),
        };
        await productService.updateListing(Number(id), updateData);

        // Upload and link any new images
        if (pendingImages.length > 0) {
          try {
            const newUrls = await uploadImagesToS3();
            if (newUrls.length > 0) {
              await linkImagesToListing(Number(id), newUrls);
            }
          } catch (imgErr) {
            console.error("Erro ao enviar imagens:", imgErr);
            await Swal.fire({
              title: "Anúncio atualizado",
              text: "O anúncio foi atualizado, mas ocorreu um erro ao enviar as imagens.",
              icon: "warning",
              confirmButtonColor: "#1e3a8a",
            });
            navigate("/dashboard");
            return;
          }
        }

        await Swal.fire({
          title: "Anúncio atualizado!",
          icon: "success",
          timer: 1500,
          showConfirmButton: false,
        });
        navigate("/dashboard");
        return;
      }

      // Create mode:
      // Step 1: Create listing with packages
      const listingData = buildListingData();
      const createdListing = await productService.createListing(listingData);
      const listingId = createdListing.id;

      // Step 2: Upload images to S3 sequentially (if any)
      let uploadedUrls: UploadedImageUrl[] = [];
      if (pendingImages.length > 0) {
        try {
          uploadedUrls = await uploadImagesToS3();
        } catch (imgErr) {
          // Listing was created but image upload failed
          console.error("Erro no upload de imagens:", imgErr);
          await Swal.fire({
            title: "Anúncio criado!",
            text: `Seu anúncio foi publicado (ID: ${listingId}), mas ocorreu um erro ao enviar as imagens. Você pode adicioná-las depois editando o anúncio.`,
            icon: "warning",
            confirmButtonColor: "#1e3a8a",
          });
          localStorage.removeItem(draftKey);
          navigate("/dashboard");
          return;
        }
      }

      // Step 3: Link images to listing sequentially
      if (uploadedUrls.length > 0) {
        try {
          await linkImagesToListing(listingId, uploadedUrls);
        } catch (linkErr) {
          console.error("Erro ao vincular imagens:", linkErr);
          await Swal.fire({
            title: "Anúncio criado!",
            text: `Seu anúncio foi publicado (ID: ${listingId}), mas ocorreu um erro ao vincular as imagens. Edite o anúncio para adicioná-las.`,
            icon: "warning",
            confirmButtonColor: "#1e3a8a",
          });
          localStorage.removeItem(draftKey);
          navigate("/dashboard");
          return;
        }
      }

      localStorage.removeItem(draftKey);

      await Swal.fire({
        title: "Anúncio publicado!",
        text: "Seu anúncio foi criado com sucesso.",
        icon: "success",
        timer: 2000,
        showConfirmButton: false,
      });
      navigate("/dashboard");
    } catch (err: any) {
      console.error("Erro ao salvar anúncio:", err);
      const message =
        err.response?.data?.detail ||
        err.response?.data?.non_field_errors?.[0] ||
        err.message ||
        "Erro ao salvar anúncio. Tente novamente.";
      await Swal.fire({
        title: "Erro",
        text: message,
        icon: "error",
        confirmButtonColor: "#1e3a8a",
      });
    } finally {
      setSubmitting(false);
    }
  };

  // ============================================
  // MELHOR ENVIO GATE SCREEN
  // ============================================

  if (meCheckLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-10 max-w-sm w-full text-center">
          <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Loader2 className="h-8 w-8 animate-spin text-blue-900" />
          </div>
          <h2 className="text-lg font-bold text-gray-900 mb-1">Verificando conexão</h2>
          <p className="text-sm text-gray-500">Aguarde enquanto verificamos sua conta Melhor Envio…</p>
        </div>
      </div>
    );
  }

  if (meCheckError) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden max-w-sm w-full">
          <div className="bg-gradient-to-r from-blue-900 to-gray-900 p-8 text-white text-center">
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <AlertCircle size={32} className="text-white" />
            </div>
            <h2 className="text-xl font-bold mb-1">Erro de conexão</h2>
            <p className="text-blue-100 text-sm">Melhor Envio</p>
          </div>
          <div className="p-8 text-center">
            <p className="text-gray-600 text-sm mb-6">
              Não foi possível verificar sua conexão com o Melhor Envio. Verifique sua conexão e tente novamente.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="w-full px-6 py-3 bg-blue-900 text-white rounded-xl font-semibold hover:bg-blue-800 active:bg-blue-950 transition cursor-pointer"
            >
              Tentar novamente
            </button>
            <button
              onClick={() => navigate(-1)}
              className="block w-full mt-3 py-2.5 text-sm text-gray-500 hover:text-gray-700 transition cursor-pointer"
            >
              Voltar
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!meConnected) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden max-w-sm w-full">
          <div className="bg-gradient-to-r from-blue-900 to-gray-900 p-8 text-white text-center">
            <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-4 backdrop-blur-sm">
              <Package size={32} className="text-white" />
            </div>
            <h2 className="text-xl font-bold mb-1">Conecte o Melhor Envio</h2>
            <p className="text-blue-100 text-sm">Necessário para anunciar produtos</p>
          </div>
          <div className="p-8 text-center">
            <p className="text-gray-600 text-sm mb-6">
              Para anunciar produtos você precisa conectar sua conta do Melhor Envio. Isso nos permite calcular fretes e processar envios para seus compradores.
            </p>
            {meConnectUrl ? (
              <a
                href={meConnectUrl}
                className="inline-flex items-center justify-center gap-2 w-full px-6 py-3 bg-blue-900 text-white rounded-xl font-semibold hover:bg-blue-800 active:bg-blue-950 transition"
              >
                <ExternalLink size={18} />
                Conectar Melhor Envio
              </a>
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                <p className="text-sm text-amber-700">
                  Não foi possível obter o link de conexão. Entre em contato com o suporte.
                </p>
              </div>
            )}
            <button
              onClick={() => navigate(-1)}
              className="block w-full mt-3 py-2.5 text-sm text-gray-500 hover:text-gray-700 transition cursor-pointer"
            >
              Voltar
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // LOADING SCREEN
  // ============================================

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-black via-gray-800 to-blue-900 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-10 max-w-sm w-full text-center">
          <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Loader2 className="h-8 w-8 animate-spin text-blue-900" />
          </div>
          <h2 className="text-lg font-bold text-gray-900 mb-1">Carregando</h2>
          <p className="text-sm text-gray-500">Preparando o formulário…</p>
        </div>
      </div>
    );
  }

  const isLastStep = currentStep === TOTAL_STEPS;
  const StepIcon = STEP_ICONS[currentStep];

  // ============================================
  // RENDER
  // ============================================

  return (
    <div className="min-h-screen bg-blue-900 pb-24">
      {/* Page banner — mirrors dashboard header style */}
      <div className="relative bg-gradient-to-br from-primary via-primary to-secundary overflow-hidden">
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 50%, #1761b9 0%, transparent 60%), radial-gradient(circle at 80% 20%, #1761b9 0%, transparent 50%)",
          }}
          aria-hidden="true"
        />
        <div className="relative max-w-2xl mx-auto px-4 sm:px-6 py-7">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-white/60 hover:text-white transition text-sm mb-4 cursor-pointer"
          >
            <ArrowLeft size={15} />
            Voltar ao painel
          </button>
          <h1 className="text-xl font-bold text-white">
            {isEditMode ? "Editar Anúncio" : "Criar Anúncio"}
          </h1>
          <p className="text-white/60 text-xs mt-0.5">
            {isEditMode
              ? "Atualize as informações do seu anúncio"
              : "Preencha as informações para publicar seu produto"}
          </p>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 sm:px-6 mt-5">

        {/* Draft notice */}
        {hasDraft && !isEditMode && (
          <div className="mb-4 bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <FileText size={15} className="text-amber-700" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-amber-800 text-sm leading-tight">
                  Rascunho encontrado
                </p>
                <p className="text-amber-700 text-xs mt-0.5">
                  Você tem um rascunho salvo em "{STEP_NAMES[draftStepRef.current] ?? `Passo ${draftStepRef.current}`}".
                </p>
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => {
                  draftJustLoadedRef.current = false;
                  setCurrentStep(draftStepRef.current);
                  setHasDraft(false);
                }}
                className="flex-1 text-xs px-3 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 active:bg-amber-800 transition font-medium cursor-pointer"
              >
                Continuar rascunho
              </button>
              <button
                onClick={discardDraft}
                className="flex-1 text-xs px-3 py-2 bg-white border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50 active:bg-amber-100 transition font-medium cursor-pointer"
              >
                Descartar
              </button>
            </div>
          </div>
        )}

        {/* Step progress */}
        <div
          className="mb-6"
          role="progressbar"
          aria-valuenow={currentStep}
          aria-valuemin={1}
          aria-valuemax={TOTAL_STEPS}
          aria-label={`Passo ${currentStep} de ${TOTAL_STEPS}: ${STEP_NAMES[currentStep]}`}
        >
          <div className="flex items-center justify-center gap-1.5 mb-2.5">
            {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((step) => (
              <div
                key={step}
                className={`rounded-full transition-all duration-300 ${
                  step === currentStep
                    ? "w-7 h-2 bg-white"
                    : step < currentStep
                      ? "w-2 h-2 bg-white/50"
                      : "w-2 h-2 bg-white/20"
                }`}
                title={STEP_NAMES[step]}
                aria-hidden="true"
              />
            ))}
          </div>
          <p className="text-center text-xs text-white/50">
            {currentStep} de {TOTAL_STEPS} — {STEP_NAMES[currentStep]}
          </p>
        </div>

        {/* Form card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100">
          {/* Step header */}
          <div className="px-6 pt-6 pb-4 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center flex-shrink-0">
                <StepIcon size={20} className="text-blue-900" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-gray-900 leading-tight">
                  {STEP_NAMES[currentStep]}
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Passo {currentStep} de {TOTAL_STEPS}
                </p>
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="px-6 py-6 space-y-4">

              {/* STEP 1 — Produto */}
              {currentStep === 1 && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-500">
                    Selecione o produto que você está anunciando.
                  </p>

                  {/* Search */}
                  <div className="relative">
                    <Search
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                    />
                    <input
                      type="text"
                      placeholder="Buscar produto…"
                      value={productSearch}
                      onChange={(e) => handleProductSearch(e.target.value)}
                      className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                    />
                    {searchingProducts && (
                      <Loader2
                        size={16}
                        className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-gray-400"
                      />
                    )}
                  </div>

                  {/* Selected product */}
                  {selectedProduct && (
                    <div className="flex items-center justify-between bg-blue-50 border border-blue-100 rounded-xl px-4 py-3">
                      <div>
                        <p className="text-sm font-semibold text-blue-900">
                          {selectedProduct.name}
                        </p>
                        {selectedProduct.code && (
                          <p className="text-xs text-blue-600">
                            {selectedProduct.code}
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={clearProduct}
                        className="text-blue-400 hover:text-blue-700 transition cursor-pointer"
                      >
                        <X size={18} />
                      </button>
                    </div>
                  )}

                  {/* Search results */}
                  {productSearch && productResults.length > 0 && (
                    <div className="border border-gray-200 rounded-xl overflow-hidden max-h-48 overflow-y-auto">
                      {productResults.map((product) => (
                        <button
                          key={product.id}
                          type="button"
                          onClick={() => selectProduct(product)}
                          className="w-full text-left px-4 py-3 hover:bg-gray-50 transition border-b border-gray-100 last:border-0 cursor-pointer"
                        >
                          <p className="text-sm font-medium text-gray-900">
                            {product.name}
                          </p>
                          {product.code && (
                            <p className="text-xs text-gray-500">
                              {product.code}
                            </p>
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* All products list */}
                  {!productSearch && !selectedProduct && (
                    <div className="border border-gray-200 rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                      {allProducts.map((product) => (
                        <button
                          key={product.id}
                          type="button"
                          onClick={() => selectProduct(product)}
                          className="w-full text-left px-4 py-3 hover:bg-gray-50 transition border-b border-gray-100 last:border-0 cursor-pointer"
                        >
                          <p className="text-sm font-medium text-gray-900">
                            {product.name}
                          </p>
                          {product.code && (
                            <p className="text-xs text-gray-500">
                              {product.code}
                            </p>
                          )}
                        </button>
                      ))}
                      {hasMoreProducts && (
                        <button
                          type="button"
                          onClick={loadMoreProducts}
                          disabled={loadingMoreProducts}
                          className="w-full py-3 text-sm text-blue-900 font-medium hover:bg-gray-50 transition disabled:opacity-50 cursor-pointer"
                        >
                          {loadingMoreProducts ? (
                            <Loader2
                              size={16}
                              className="animate-spin mx-auto"
                            />
                          ) : (
                            "Carregar mais"
                          )}
                        </button>
                      )}
                    </div>
                  )}

                  {errors.product && (
                    <p className="text-sm text-red-500">{errors.product}</p>
                  )}
                </div>
              )}

              {/* STEP 2 — Título */}
              {currentStep === 2 && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Título do anúncio
                  </label>
                  <input
                    type="text"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    maxLength={150}
                    placeholder="Ex: Monitor Ultrawide LG 34'' 144Hz"
                    className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                  />
                  <div className="flex items-center justify-between">
                    {errors.title ? (
                      <p className="text-sm text-red-500">{errors.title}</p>
                    ) : (
                      <span />
                    )}
                    <p className="text-xs text-gray-400">
                      {formData.title.length}/150
                    </p>
                  </div>
                </div>
              )}

              {/* STEP 3 — Descrição */}
              {currentStep === 3 && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Descrição
                  </label>
                  <textarea
                    name="description"
                    value={formData.description}
                    onChange={handleChange}
                    maxLength={255}
                    rows={5}
                    placeholder="Descreva o produto com detalhes relevantes…"
                    className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition resize-none"
                  />
                  <div className="flex items-center justify-between">
                    {errors.description ? (
                      <p className="text-sm text-red-500">
                        {errors.description}
                      </p>
                    ) : (
                      <span />
                    )}
                    <p className="text-xs text-gray-400">
                      {formData.description.length}/255
                    </p>
                  </div>
                </div>
              )}

              {/* STEP 4 — Marca & Condição */}
              {currentStep === 4 && (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Marca
                    </label>
                    <select
                      name="brand"
                      value={formData.brand}
                      onChange={handleChange}
                      className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition bg-white"
                    >
                      <option value="">Selecione uma marca</option>
                      {filterOptions?.brands.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                    {errors.brand && (
                      <p className="text-sm text-red-500">{errors.brand}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Condição
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {filterOptions?.conditions.map((c) => (
                        <label
                          key={c.id}
                          className={`flex items-center gap-3 px-4 py-3 border-2 rounded-xl cursor-pointer transition ${
                            formData.condition === String(c.id)
                              ? "border-blue-900 bg-blue-50"
                              : "border-gray-200 hover:border-gray-300"
                          }`}
                        >
                          <input
                            type="radio"
                            name="condition"
                            value={c.id}
                            checked={formData.condition === String(c.id)}
                            onChange={handleChange}
                            className="sr-only"
                          />
                          {formData.condition === String(c.id) ? (
                            <CheckCircle
                              size={18}
                              className="text-blue-900 flex-shrink-0"
                            />
                          ) : (
                            <div className="w-[18px] h-[18px] border-2 border-gray-300 rounded-full flex-shrink-0" />
                          )}
                          <span
                            className={`text-sm font-medium ${
                              formData.condition === String(c.id)
                                ? "text-blue-900"
                                : "text-gray-700"
                            }`}
                          >
                            {c.name}
                          </span>
                        </label>
                      ))}
                    </div>
                    {errors.condition && (
                      <p className="text-sm text-red-500">{errors.condition}</p>
                    )}
                  </div>
                </div>
              )}

              {/* STEP 5 — Preço & Quantidade */}
              {currentStep === 5 && (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Preço (R$)
                    </label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                        R$
                      </span>
                      <input
                        type="number"
                        name="price"
                        value={formData.price}
                        onChange={handleChange}
                        min="0.01"
                        step="0.01"
                        placeholder="0,00"
                        className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                      />
                    </div>
                    {errors.price && (
                      <p className="text-sm text-red-500">{errors.price}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Quantidade em estoque
                    </label>
                    <input
                      type="number"
                      name="quantity"
                      value={formData.quantity}
                      onChange={handleChange}
                      min="1"
                      step="1"
                      className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                    />
                  </div>
                </div>
              )}

              {/* STEP 6 — Dimensões do Pacote */}
              {currentStep === 6 && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-500">
                    Informe as dimensões do pacote que será enviado. Esses dados
                    são usados para calcular o frete.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700">
                        Peso (kg)
                      </label>
                      <input
                        type="number"
                        name="weight_kg"
                        value={formData.weight_kg}
                        onChange={handleChange}
                        min="0.01"
                        step="0.01"
                        placeholder="0.00"
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                      />
                      {errors.weight_kg && (
                        <p className="text-xs text-red-500">
                          {errors.weight_kg}
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700">
                        Altura (cm)
                      </label>
                      <input
                        type="number"
                        name="height_cm"
                        value={formData.height_cm}
                        onChange={handleChange}
                        min="0.1"
                        step="0.1"
                        placeholder="0.0"
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                      />
                      {errors.height_cm && (
                        <p className="text-xs text-red-500">
                          {errors.height_cm}
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700">
                        Largura (cm)
                      </label>
                      <input
                        type="number"
                        name="width_cm"
                        value={formData.width_cm}
                        onChange={handleChange}
                        min="0.1"
                        step="0.1"
                        placeholder="0.0"
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                      />
                      {errors.width_cm && (
                        <p className="text-xs text-red-500">
                          {errors.width_cm}
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700">
                        Comprimento (cm)
                      </label>
                      <input
                        type="number"
                        name="length_cm"
                        value={formData.length_cm}
                        onChange={handleChange}
                        min="0.1"
                        step="0.1"
                        placeholder="0.0"
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                      />
                      {errors.length_cm && (
                        <p className="text-xs text-red-500">
                          {errors.length_cm}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Descrição do pacote{" "}
                      <span className="text-gray-400 font-normal">
                        (opcional)
                      </span>
                    </label>
                    <input
                      type="text"
                      name="package_description"
                      value={formData.package_description}
                      onChange={handleChange}
                      maxLength={100}
                      placeholder="Ex: Caixa com espuma protetora"
                      className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                    />
                  </div>
                </div>
              )}

              {/* STEP 7 — Imagens */}
              {currentStep === 7 && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-500">
                    Adicione fotos do produto. A primeira imagem será a capa do
                    anúncio.{" "}
                    <span className="font-medium">
                      Máximo {MAX_IMAGES} imagens.
                    </span>
                  </p>

                  {/* Drag & drop zone */}
                  <label
                    className={`block border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                      isDragging
                        ? "border-blue-900 bg-blue-50 scale-[1.01]"
                        : "border-gray-200 hover:border-blue-300 hover:bg-gray-50/50"
                    }`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    <input
                      type="file"
                      multiple
                      accept="image/jpeg,image/png,image/webp"
                      onChange={handleFileSelect}
                      className="sr-only"
                    />
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3 transition-colors ${isDragging ? "bg-blue-100" : "bg-gray-100"}`}>
                      <ImagePlus
                        size={22}
                        className={isDragging ? "text-blue-900" : "text-gray-400"}
                      />
                    </div>
                    <p className="text-sm font-semibold text-gray-700">
                      {isDragging ? "Solte as imagens aqui" : "Clique para selecionar ou arraste"}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      JPEG, PNG ou WebP · Máx {IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB por imagem
                    </p>
                  </label>

                  {uploadError && (
                    <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-start gap-2">
                      <AlertCircle
                        size={16}
                        className="text-red-500 flex-shrink-0 mt-0.5"
                      />
                      <p className="text-sm text-red-700">{uploadError}</p>
                    </div>
                  )}

                  {/* Uploading progress */}
                  {uploading && (
                    <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Loader2
                          size={16}
                          className="animate-spin text-blue-900"
                        />
                        <p className="text-sm text-blue-900 font-medium">
                          Enviando imagem {uploadProgress.current} de{" "}
                          {uploadProgress.total}…
                        </p>
                      </div>
                      <div className="w-full bg-blue-100 rounded-full h-1.5">
                        <div
                          className="bg-blue-900 h-1.5 rounded-full transition-all duration-300"
                          style={{
                            width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Existing images (edit mode) */}
                  {existingImages.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                        Imagens atuais
                      </p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {existingImages.map((img) => (
                          <div
                            key={img.id}
                            className={`relative rounded-xl overflow-hidden aspect-square border-2 transition ${
                              img.is_primary
                                ? "border-blue-900"
                                : "border-transparent"
                            }`}
                          >
                            <img
                              src={img.image_url}
                              alt="Imagem existente"
                              className="w-full h-full object-cover"
                            />
                            {img.is_primary && (
                              <div className="absolute top-1 left-1 bg-blue-900 text-white text-xs px-1.5 py-0.5 rounded-md flex items-center gap-1">
                                <Star size={10} />
                                Capa
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pending images */}
                  {pendingImages.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                        Novas imagens ({pendingImages.length})
                      </p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {pendingImages.map((img) => (
                          <div
                            key={img.id}
                            className={`relative rounded-xl overflow-hidden aspect-square border-2 transition ${
                              img.isPrimary
                                ? "border-blue-900"
                                : "border-transparent"
                            }`}
                          >
                            <img
                              src={img.previewUrl}
                              alt="Preview"
                              className="w-full h-full object-cover"
                            />

                            {/* Primary badge */}
                            {img.isPrimary && (
                              <div className="absolute top-1 left-1 bg-blue-900 text-white text-xs px-1.5 py-0.5 rounded-md flex items-center gap-1">
                                <Star size={10} />
                                Capa
                              </div>
                            )}

                            {/* Actions overlay */}
                            <div className="absolute inset-0 bg-black/0 hover:bg-black/30 transition flex items-center justify-center gap-2 opacity-0 hover:opacity-100">
                              {!img.isPrimary && (
                                <button
                                  type="button"
                                  onClick={() => setPendingPrimary(img.id)}
                                  title="Definir como capa"
                                  className="w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow hover:bg-blue-50 transition cursor-pointer"
                                >
                                  <Star size={14} className="text-blue-900" />
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => removePendingImage(img.id)}
                                title="Remover imagem"
                                className="w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow hover:bg-red-50 transition cursor-pointer"
                              >
                                <Trash2 size={14} className="text-red-500" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {pendingImages.length === 0 && existingImages.length === 0 && (
                    <p className="text-sm text-gray-400 text-center py-2">
                      Nenhuma imagem selecionada. As imagens são opcionais, mas
                      aumentam as chances de venda.
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Navigation buttons */}
            <div className="px-6 pb-6 pt-2 flex items-center gap-3">
              {currentStep > 1 ? (
                <button
                  type="button"
                  onClick={handleBack}
                  disabled={submitting || uploading}
                  className="flex items-center gap-2 px-5 py-2.5 border border-gray-200 text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 active:bg-gray-100 transition disabled:opacity-50 cursor-pointer"
                >
                  <ArrowLeft size={16} />
                  Voltar
                </button>
              ) : (
                <div />
              )}

              <button
                type="submit"
                disabled={submitting || uploading}
                className="flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 active:bg-blue-950 transition disabled:opacity-60 cursor-pointer ml-auto min-w-[130px]"
              >
                {submitting || uploading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>{uploading ? "Enviando…" : "Publicando…"}</span>
                  </>
                ) : isLastStep ? (
                  <>
                    <CheckCircle size={16} />
                    <span>{isEditMode ? "Salvar alterações" : "Publicar Anúncio"}</span>
                  </>
                ) : (
                  <>
                    <span>Próximo</span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
