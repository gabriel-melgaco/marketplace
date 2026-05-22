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
  Plus,
  Truck,
  CreditCard,
} from "lucide-react";
import { productService } from "@/services/productService";
import { storageService, IMAGE_UPLOAD_LIMITS } from "@/services/storageService";
import { listingImageService } from "@/services/listingImageService";
import { logisticsService } from "@/services/logisticsService";
import { stripeConnectService } from "@/services/stripeConnectService";
import { getMarketplaceFee } from "@/services/configService";
import type {
  FilterOptionsResponse,
  MarketplaceListingImage,
  UpdateListingRequest,
  FormData,
  PendingImage,
  ProductListItem,
  ListingPackageRequest,
  ShippingMethod,
} from "@/types/product";
import { INITIAL_FORMDATA } from "@/constants/brazilianStates";
import {
  validateStep as validateStepHelper,
  validatePackageDraft as validatePackageDraftHelper,
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
  packages: 6,
};

const STEP_NAMES: Record<number, string> = {
  1: "Produto",
  2: "Título",
  3: "Descrição",
  4: "Marca e Condição",
  5: "Preço",
  6: "Pacotes & Envio",
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

interface PackageEntry extends ListingPackageRequest {
  _key: string;
}

interface DraftData {
  step: number;
  formData: FormData;
  packages?: PackageEntry[];
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
  const [mePolling, setMePolling] = useState(false);
  const mePopupRef = useRef<Window | null>(null);
  const mePollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );

  // Stripe Connect gate
  const [stripeCheckLoading, setStripeCheckLoading] = useState(true);
  const [stripeConnected, setStripeConnected] = useState(false);
  const [stripeCheckError, setStripeCheckError] = useState(false);
  const [stripeOnboardingLoading, setStripeOnboardingLoading] = useState(false);

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
  const searchAbortControllerRef = useRef<AbortController | null>(null);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draftProductRestoredRef = useRef(false);

  // Draft timing refs
  const draftStepRef = useRef<number>(1);
  const draftJustLoadedRef = useRef(false);

  // Holds the ID of the listing created at the step 6 → 7 transition
  // (create mode only). Never persisted to localStorage — if the user
  // restores a draft the listing ID is orphaned and a fresh creation is needed.
  const [createdListingId, setCreatedListingId] = useState<number | null>(null);

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
  const [platformFeePercentage, setPlatformFeePercentage] = useState<
    number | null
  >(null);
  const [packages, setPackages] = useState<PackageEntry[]>([]);
  const [showPackageModal, setShowPackageModal] = useState(false);
  const [editingPackageIndex, setEditingPackageIndex] = useState<number | null>(
    null,
  );
  const [packageDraft, setPackageDraft] = useState<ListingPackageRequest>({
    weight_kg: "",
    height_cm: "",
    width_cm: "",
    length_cm: "",
    description: "",
  });
  const [packageDraftErrors, setPackageDraftErrors] = useState<
    Record<string, string>
  >({});

  const draftKey = isEditMode ? `listing_draft_${id}` : "listing_draft";

  // ============================================
  // MELHOR ENVIO + STRIPE GATE CHECK (parallel)
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
          try {
            const connectData =
              await logisticsService.getMelhorEnvioConnectUrl();
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

    async function checkStripeConnection() {
      setStripeCheckLoading(true);
      setStripeCheckError(false);
      try {
        const status = await stripeConnectService.getAccountStatus();
        setStripeConnected(
          status.has_account && status.ready_to_receive_payments,
        );
      } catch {
        setStripeCheckError(true);
      } finally {
        setStripeCheckLoading(false);
      }
    }

    checkMelhorEnvioConnection();
    checkStripeConnection();
  }, []);

  // Cleanup polling and popup on unmount
  useEffect(() => {
    return () => {
      if (mePollingIntervalRef.current) {
        clearInterval(mePollingIntervalRef.current);
      }
      if (mePopupRef.current && !mePopupRef.current.closed) {
        mePopupRef.current.close();
      }
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current);
      }
    };
  }, []);

  /**
   * Opens the Melhor Envio OAuth flow in a popup window and polls
   * GET /logistics/me/status/ every 3 s until connected.
   * This keeps the main window alive so the user stays in the form.
   */
  const startMeConnection = useCallback(() => {
    if (!meConnectUrl) return;

    const popup = window.open(
      meConnectUrl,
      "melhorenvio_oauth",
      "width=640,height=720,left=200,top=100,toolbar=no,menubar=no,scrollbars=yes",
    );
    mePopupRef.current = popup;
    setMePolling(true);

    const MAX_POLLS = 20; // 60 s total
    let pollCount = 0;

    mePollingIntervalRef.current = setInterval(async () => {
      pollCount += 1;

      try {
        const status = await logisticsService.getMelhorEnvioStatus();
        if (status.connected && !status.is_expired) {
          clearInterval(mePollingIntervalRef.current!);
          mePollingIntervalRef.current = null;
          if (mePopupRef.current && !mePopupRef.current.closed) {
            mePopupRef.current.close();
          }
          setMePolling(false);
          setMeConnected(true);
          return;
        }
      } catch {
        // Ignore transient network errors during polling
      }

      if (mePopupRef.current?.closed) {
        clearInterval(mePollingIntervalRef.current!);
        mePollingIntervalRef.current = null;
        setMePolling(false);
        return;
      }

      if (pollCount >= MAX_POLLS) {
        clearInterval(mePollingIntervalRef.current!);
        mePollingIntervalRef.current = null;
        if (mePopupRef.current && !mePopupRef.current.closed) {
          mePopupRef.current.close();
        }
        setMePolling(false);
      }
    }, 3000);
  }, [meConnectUrl]);

  const startStripeOnboarding = useCallback(async () => {
    if (stripeOnboardingLoading) return;
    setStripeOnboardingLoading(true);
    try {
      // Ensure account exists first — may already exist, that's fine
      try {
        await stripeConnectService.createConnectedAccount();
      } catch {
        // Account may already exist — this is expected
      }
      const link = await stripeConnectService.getOnboardingLink();
      window.location.href = link.url;
    } catch (err: unknown) {
      Swal.fire({
        icon: "error",
        title: "Erro",
        text: "Não foi possível iniciar o cadastro Stripe. Tente novamente.",
        confirmButtonColor: "#1e3a5f",
      });
    } finally {
      setStripeOnboardingLoading(false);
    }
  }, [stripeOnboardingLoading]);

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
        if (draft.packages && draft.packages.length > 0) {
          setPackages(
            draft.packages.map((pkg) => ({
              ...pkg,
              _key: (pkg as PackageEntry)._key ?? crypto.randomUUID(),
            })),
          );
        }
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
        packages,
      };
      localStorage.setItem(draftKey, JSON.stringify(draft));
    } catch (err) {
      console.error("Error saving draft:", err);
    }
  }, [currentStep, formData, packages, draftKey, isEditMode]);

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
    setPackages([]);
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

  // Fetch marketplace fee once on mount (no auth required)
  useEffect(() => {
    getMarketplaceFee()
      .then(setPlatformFeePercentage)
      .catch((err) => {
        console.error("Erro ao carregar taxa da plataforma:", err);
      });
  }, []);

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
          shipping_method: (listing.shipping_method ||
            "both") as ShippingMethod,
        });
        if (listing.packages && listing.packages.length > 0) {
          setPackages(
            listing.packages.map((pkg) => ({
              weight_kg: pkg.weight_kg || "",
              height_cm: pkg.height_cm || "",
              width_cm: pkg.width_cm || "",
              length_cm: pkg.length_cm || "",
              description: pkg.description || "",
              _key: crypto.randomUUID(),
            })),
          );
        } else if (listing.weight_kg) {
          setPackages([
            {
              weight_kg: listing.weight_kg || "",
              height_cm: listing.height_cm || "",
              width_cm: listing.width_cm || "",
              length_cm: listing.length_cm || "",
              description: "",
              _key: crypto.randomUUID(),
            },
          ]);
        }
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

  const handleProductSearch = useCallback((term: string) => {
    setProductSearch(term);

    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = null;
    }

    if (!term.trim()) {
      setProductResults([]);
      setSearchingProducts(false);
      if (searchAbortControllerRef.current) {
        searchAbortControllerRef.current.abort();
        searchAbortControllerRef.current = null;
      }
      return;
    }

    if (searchAbortControllerRef.current) {
      searchAbortControllerRef.current.abort();
    }

    setSearchingProducts(true);

    searchDebounceRef.current = setTimeout(async () => {
      const controller = new AbortController();
      searchAbortControllerRef.current = controller;

      try {
        const response = await productService.getProducts({
          search: term.trim(),
        });
        if (!controller.signal.aborted) {
          setProductResults(response.results);
        }
      } catch (err: unknown) {
        const e = err as { name?: string };
        if (e.name !== "AbortError" && e.name !== "CanceledError") {
          console.error("Erro ao buscar produtos:", err);
        }
      } finally {
        if (!controller.signal.aborted) {
          setSearchingProducts(false);
        }
      }
    }, 300);
  }, []);

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
    const newErrors = validateStepHelper(
      step,
      formData,
      step === 6 ? packages : undefined,
    );
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
          isPrimary: totalImages === 0 && newImages.length === 0,
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

  const uploadImagesToS3 = useCallback(async (): Promise<
    UploadedImageUrl[]
  > => {
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
  }, [pendingImages]);

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
    () =>
      buildListingDataHelper(
        formData,
        packages.map(({ _key: _, ...pkg }) => pkg),
      ),
    [formData, packages],
  );

  // ============================================
  // NAVIGATION
  // ============================================

  const handleContinue = async () => {
    if (!validateCurrentStep(currentStep)) return;

    // ── Step 6 → 7 in CREATE mode ──────────────────────────────────────────
    // Create the listing before the user reaches the image step so that we
    // have a valid listing ID to attach images to.
    // In edit mode the listing already exists; just advance normally.
    if (currentStep === 6 && !isEditMode) {
      // If the listing was already created (e.g. user went back and came
      // forward again), skip creation and advance directly.
      if (createdListingId !== null) {
        setCurrentStep(7);
        setErrors({});
        setUploadError(null);
        return;
      }

      setSubmitting(true);
      setUploadError(null);

      try {
        const listingData = buildListingData();
        const createdListing = await productService.createListing(listingData);
        const newListingId = createdListing.id;

        if (!newListingId) {
          throw new Error("A API não retornou o ID do anúncio.");
        }

        setCreatedListingId(newListingId);
        setCurrentStep(7);
        setErrors({});
        setUploadError(null);
      } catch (err: unknown) {
        const e = err as {
          response?: {
            data?: { detail?: string; non_field_errors?: string[] };
          };
          message?: string;
        };
        const message =
          e.response?.data?.detail ||
          e.response?.data?.non_field_errors?.[0] ||
          e.message ||
          "Erro ao criar anúncio.";
        await Swal.fire({
          title: "Erro",
          text: message,
          icon: "error",
          confirmButtonColor: "#1e3a8a",
        });
      } finally {
        setSubmitting(false);
      }

      return;
    }

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

    // Steps 1–6: delegate to handleContinue instead of submitting.
    if (currentStep < TOTAL_STEPS) {
      handleContinue();
      return;
    }

    // ── STEP 7 SUBMIT ────────────────────────────────────────────────────────
    // CREATE mode: the listing was already created when the user advanced
    // from step 6. We only need to upload images and link them.
    //
    // EDIT mode: call updateListing first, then upload images.

    setSubmitting(true);
    setUploadError(null);

    try {
      if (isEditMode && id) {
        // ── Edit mode ────────────────────────────────────────────────────
        const allErrors: Record<string, string> = {};
        for (let step = 1; step <= 6; step++) {
          const stepErrors = validateStepHelper(
            step,
            formData,
            step === 6 ? packages : undefined,
          );
          Object.assign(allErrors, stepErrors);
        }
        if (Object.keys(allErrors).length > 0) {
          setErrors(allErrors);
          const targetStep = Object.keys(allErrors).reduce((lowest, field) => {
            const step = FIELD_TO_STEP[field] ?? 1;
            return step < lowest ? step : lowest;
          }, 6);
          setCurrentStep(targetStep);
          setSubmitting(false);
          return;
        }

        const updateData: UpdateListingRequest = {
          ...buildListingData(),
        };
        await productService.updateListing(Number(id), updateData);

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

      // ── Create mode ──────────────────────────────────────────────────────
      // The listing was created at the step 6 → 7 transition.
      // If it is somehow missing, send the user back to step 6.
      if (createdListingId === null) {
        await Swal.fire({
          title: "Erro inesperado",
          text: "O anúncio não foi criado corretamente. Por favor, retorne ao passo anterior e tente novamente.",
          icon: "error",
          confirmButtonColor: "#1e3a8a",
        });
        setCurrentStep(6);
        setSubmitting(false);
        return;
      }

      const listingId = createdListingId;

      let uploadedUrls: UploadedImageUrl[] = [];
      if (pendingImages.length > 0) {
        try {
          uploadedUrls = await uploadImagesToS3();
        } catch (imgErr) {
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
    } catch (err: unknown) {
      console.error("Erro ao salvar anúncio:", err);
      const e = err as {
        response?: { data?: { detail?: string; non_field_errors?: string[] } };
        message?: string;
      };
      const message =
        e.response?.data?.detail ||
        e.response?.data?.non_field_errors?.[0] ||
        e.message ||
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
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div
          className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-10 max-w-sm w-full text-center"
          role="status"
          aria-live="polite"
        >
          <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Loader2
              size={28}
              className="animate-spin text-gold"
              aria-hidden="true"
            />
          </div>
          <h2 className="font-display text-xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
            Verificando conexão
          </h2>
          <p className="text-ink-2 text-sm leading-relaxed">
            Aguarde enquanto verificamos sua conta Melhor Envio…
          </p>
        </div>
      </div>
    );
  }

  if (meCheckError) {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div
          className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden max-w-sm w-full"
          role="alert"
        >
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <AlertCircle
                size={28}
                className="text-red-400"
                aria-hidden="true"
              />
            </div>
            <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Erro de conexão
            </h2>
            <p className="text-ink-2 text-sm">Melhor Envio</p>
          </div>
          <div className="p-6 md:p-8 text-center space-y-3">
            <p className="text-ink-2 text-sm leading-relaxed mb-3">
              Não foi possível verificar sua conexão com o Melhor Envio.
              Verifique sua conexão e tente novamente.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="w-full px-6 py-3 bg-gold text-gold-deep rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
            >
              Tentar novamente
            </button>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="block w-full py-2.5 text-sm text-ink-2 hover:text-ink-1 transition-colors"
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
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden w-full max-w-md mx-auto">
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Package size={28} className="text-gold" aria-hidden="true" />
            </div>
            <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Conecte o Melhor Envio
            </h2>
            <p className="text-ink-2 text-sm">
              Necessário para anunciar produtos
            </p>
          </div>
          <div className="p-6 md:p-8 text-center">
            {mePolling ? (
              <>
                <div
                  className="flex items-center justify-center gap-2 mb-3"
                  role="status"
                  aria-live="polite"
                >
                  <Loader2
                    size={20}
                    className="animate-spin text-gold"
                    aria-hidden="true"
                  />
                  <p className="text-sm font-semibold text-ink-1">
                    Aguardando autorização…
                  </p>
                </div>
                <p className="text-xs text-ink-3 mb-6 leading-relaxed">
                  Conclua a autorização na janela do Melhor Envio que foi
                  aberta. Esta tela atualizará automaticamente.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    if (mePollingIntervalRef.current) {
                      clearInterval(mePollingIntervalRef.current);
                      mePollingIntervalRef.current = null;
                    }
                    if (mePopupRef.current && !mePopupRef.current.closed) {
                      mePopupRef.current.close();
                    }
                    setMePolling(false);
                  }}
                  className="w-full px-6 py-2.5 bg-bg-2 border border-white/10 text-ink-1 rounded-xl text-sm font-medium hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
                >
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <p className="text-ink-2 text-sm leading-relaxed mb-6">
                  Para anunciar produtos você precisa conectar sua conta do
                  Melhor Envio. Isso nos permite calcular fretes e processar
                  envios para seus compradores.
                </p>
                {meConnectUrl ? (
                  <button
                    type="button"
                    onClick={startMeConnection}
                    className="inline-flex items-center justify-center gap-2 w-full px-6 py-3 bg-gold text-gold-deep rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
                  >
                    <ExternalLink size={18} aria-hidden="true" />
                    Conectar Melhor Envio
                  </button>
                ) : (
                  <div
                    role="alert"
                    className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3"
                  >
                    <p className="text-sm text-red-400">
                      Não foi possível obter o link de conexão. Entre em contato
                      com o suporte.
                    </p>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => navigate(-1)}
                  className="block w-full mt-3 py-2.5 text-sm text-ink-2 hover:text-ink-1 transition-colors"
                >
                  Voltar
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // STRIPE CONNECT GATE SCREENS
  // ============================================

  if (stripeCheckLoading) {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div
          className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-10 max-w-sm w-full text-center"
          role="status"
          aria-live="polite"
        >
          <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Loader2
              size={28}
              className="animate-spin text-gold"
              aria-hidden="true"
            />
          </div>
          <h2 className="font-display text-xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
            Verificando conexão
          </h2>
          <p className="text-ink-2 text-sm leading-relaxed">
            Verificando conta Stripe…
          </p>
        </div>
      </div>
    );
  }

  if (stripeCheckError) {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div
          className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden max-w-sm w-full"
          role="alert"
        >
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-red-500/10 border border-red-500/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <AlertCircle
                size={28}
                className="text-red-400"
                aria-hidden="true"
              />
            </div>
            <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Erro de conexão
            </h2>
            <p className="text-ink-2 text-sm">Stripe Connect</p>
          </div>
          <div className="p-6 md:p-8 text-center space-y-3">
            <p className="text-ink-2 text-sm leading-relaxed mb-3">
              Não foi possível verificar sua conta Stripe. Verifique sua conexão
              e tente novamente.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="w-full px-6 py-3 bg-gold text-gold-deep rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1"
            >
              Tentar novamente
            </button>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="block w-full py-2.5 text-sm text-ink-2 hover:text-ink-1 transition-colors"
            >
              Voltar
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!stripeConnected) {
    return (
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden w-full max-w-md mx-auto">
          <div className="bg-bg-2 p-6 md:p-8 border-b border-white/10 text-center">
            <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <CreditCard size={28} className="text-gold" aria-hidden="true" />
            </div>
            <h2 className="font-display text-xl md:text-2xl font-bold text-ink-1 tracking-[-0.02em] mb-1">
              Conecte sua conta Stripe
            </h2>
            <p className="text-ink-2 text-sm">
              Necessário para receber pagamentos
            </p>
          </div>
          <div className="p-6 md:p-8 text-center">
            <p className="text-ink-2 text-sm leading-relaxed mb-6">
              Para anunciar produtos você precisa conectar uma conta Stripe.
              Isso nos permite processar pagamentos e repassar os valores das
              suas vendas.
            </p>
            <button
              type="button"
              onClick={startStripeOnboarding}
              disabled={stripeOnboardingLoading}
              className="inline-flex items-center justify-center gap-2 w-full px-6 py-3 bg-gold text-gold-deep rounded-xl font-semibold text-sm hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {stripeOnboardingLoading ? (
                <>
                  <Loader2
                    size={18}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                  Aguarde...
                </>
              ) : (
                <>
                  <CreditCard size={18} aria-hidden="true" />
                  Conectar Stripe
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="block w-full mt-3 py-2.5 text-sm text-ink-2 hover:text-ink-1 transition-colors"
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
      <div className="min-h-screen bg-bg-0 flex items-center justify-center p-4">
        <div
          className="bg-bg-1 border border-white/10 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-10 max-w-sm w-full text-center"
          role="status"
          aria-live="polite"
        >
          <div className="w-16 h-16 bg-gold/10 border border-gold/30 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <Loader2
              size={28}
              className="animate-spin text-gold"
              aria-hidden="true"
            />
          </div>
          <h2 className="font-display text-xl font-bold text-ink-1 tracking-[-0.02em] mb-2">
            Carregando
          </h2>
          <p className="text-ink-2 text-sm leading-relaxed">
            Preparando o formulário…
          </p>
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
    <div className="min-h-screen bg-bg-0 pb-24">
      {/* Page banner */}
      <div className="relative bg-bg-1 border-b border-white/10 overflow-hidden">
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 50%, rgba(245, 158, 11, 0.08) 0%, transparent 60%), radial-gradient(circle at 80% 20%, rgba(245, 158, 11, 0.05) 0%, transparent 50%)",
          }}
          aria-hidden="true"
        />
        <div className="relative max-w-2xl mx-auto px-4 sm:px-6 py-7">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-ink-2 hover:text-ink-1 transition-colors text-sm mb-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1 rounded-md px-1 -ml-1"
          >
            <ArrowLeft size={15} aria-hidden="true" />
            Voltar ao painel
          </button>
          <h1 className="font-display text-2xl md:text-3xl font-bold text-ink-1 tracking-[-0.02em]">
            {isEditMode ? "Editar Anúncio" : "Criar Anúncio"}
          </h1>
          <p className="text-ink-2 text-sm mt-1.5 leading-relaxed">
            {isEditMode
              ? "Atualize as informações do seu anúncio"
              : "Preencha as informações para publicar seu produto"}
          </p>
        </div>
      </div>

      <div className="w-full max-w-xl mx-auto px-4 sm:px-6 mt-5">
        {/* Draft notice */}
        {hasDraft && !isEditMode && (
          <div
            role="status"
            className="mb-4 bg-bg-1 border border-gold/30 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] p-4"
          >
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-gold/10 border border-gold/30 flex items-center justify-center shrink-0 mt-0.5">
                <FileText size={16} className="text-gold" aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-ink-1 text-sm leading-tight">
                  Rascunho encontrado
                </p>
                <p className="text-ink-2 text-xs mt-1 leading-relaxed">
                  Você tem um rascunho salvo em "
                  {STEP_NAMES[draftStepRef.current] ??
                    `Passo ${draftStepRef.current}`}
                  ".
                </p>
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={() => {
                  draftJustLoadedRef.current = false;
                  setCurrentStep(draftStepRef.current);
                  setHasDraft(false);
                }}
                className="flex-1 text-xs px-3 py-2 bg-gold text-gold-deep rounded-xl font-semibold hover:bg-gold/90 active:bg-gold/80 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0"
              >
                Continuar rascunho
              </button>
              <button
                type="button"
                onClick={discardDraft}
                className="flex-1 text-xs px-3 py-2 bg-bg-2 border border-white/10 text-ink-1 rounded-xl font-medium hover:bg-bg-3 hover:border-white/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-0"
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
            {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map(
              (step) => (
                <div
                  key={step}
                  className={`rounded-full transition-all duration-300 ${
                    step === currentStep
                      ? "w-7 h-2 bg-gold"
                      : step < currentStep
                        ? "w-2 h-2 bg-gold/50"
                        : "w-2 h-2 bg-white/10"
                  }`}
                  title={STEP_NAMES[step]}
                  aria-hidden="true"
                />
              ),
            )}
          </div>
          <p className="text-center text-xs text-ink-3">
            {currentStep} de {TOTAL_STEPS} — {STEP_NAMES[currentStep]}
          </p>
        </div>

        {/* Form card */}
        <div className="bg-bg-1 rounded-2xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] border border-white/10">
          {/* Step header */}
          <div className="px-6 pt-6 pb-4 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center shrink-0">
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
                              className="text-blue-900 shrink-0"
                            />
                          ) : (
                            <div className="w-4.5 h-4.5 border-2 border-gray-300 rounded-full shrink-0" />
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
                    {(() => {
                      const priceNum = Number(formData.price);
                      if (
                        !formData.price ||
                        isNaN(priceNum) ||
                        priceNum <= 0 ||
                        platformFeePercentage === null ||
                        platformFeePercentage === 0
                      )
                        return null;
                      const netValue =
                        Math.round(
                          priceNum * (1 - platformFeePercentage / 100) * 100,
                        ) / 100;
                      return (
                        <p className="text-sm text-green-700">
                          Você irá receber{" "}
                          <span className="font-semibold">
                            R${" "}
                            {netValue.toLocaleString("pt-BR", {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </span>{" "}
                          <span className="text-green-600">
                            (-{platformFeePercentage}%)
                          </span>
                        </p>
                      );
                    })()}
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

              {/* STEP 6 — Pacotes & Envio */}
              {currentStep === 6 && (
                <div className="space-y-6">
                  {/* Shipping Method */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700">
                      Método de envio
                    </label>
                    <div
                      className="grid grid-cols-1 sm:grid-cols-3 gap-2"
                      role="radiogroup"
                      aria-label="Método de envio"
                    >
                      {[
                        { value: "both" as ShippingMethod, label: "Ambos" },
                        {
                          value: "melhor_envio" as ShippingMethod,
                          label: "Somente Melhor Envio",
                        },
                        {
                          value: "in_person" as ShippingMethod,
                          label: "Somente Presencial",
                        },
                      ].map((opt) => (
                        <label
                          key={opt.value}
                          className={`flex items-center gap-2.5 px-4 py-3 border-2 rounded-xl cursor-pointer transition ${
                            formData.shipping_method === opt.value
                              ? "border-blue-900 bg-blue-50"
                              : "border-gray-200 hover:border-gray-300"
                          }`}
                        >
                          <input
                            type="radio"
                            name="shipping_method"
                            value={opt.value}
                            checked={formData.shipping_method === opt.value}
                            onChange={() =>
                              setFormData((prev) => ({
                                ...prev,
                                shipping_method: opt.value,
                              }))
                            }
                            className="sr-only"
                          />
                          <Truck
                            size={16}
                            className={
                              formData.shipping_method === opt.value
                                ? "text-blue-900 shrink-0"
                                : "text-gray-400 shrink-0"
                            }
                          />
                          <span
                            className={`text-sm font-medium ${
                              formData.shipping_method === opt.value
                                ? "text-blue-900"
                                : "text-gray-700"
                            }`}
                          >
                            {opt.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Package list */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="block text-sm font-medium text-gray-700">
                        Pacotes{" "}
                        <span className="text-gray-400 font-normal">
                          ({packages.length})
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setPackageDraft({
                            weight_kg: "",
                            height_cm: "",
                            width_cm: "",
                            length_cm: "",
                            description: "",
                          });
                          setPackageDraftErrors({});
                          setEditingPackageIndex(null);
                          setShowPackageModal(true);
                        }}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-900 text-white rounded-lg hover:bg-blue-800 transition cursor-pointer"
                      >
                        <Plus size={14} />
                        Adicionar Pacote
                      </button>
                    </div>

                    <p className="text-sm text-gray-500">
                      Informe as dimensões de cada pacote que será enviado.
                      Esses dados são usados para calcular o frete.
                    </p>

                    {errors.packages && (
                      <p className="text-sm text-red-500">{errors.packages}</p>
                    )}

                    {packages.length === 0 && (
                      <div className="border-2 border-dashed border-gray-200 rounded-xl py-8 text-center">
                        <Package
                          size={28}
                          className="mx-auto text-gray-300 mb-2"
                        />
                        <p className="text-sm text-gray-400">
                          Nenhum pacote adicionado ainda.
                        </p>
                        <p className="text-xs text-gray-300 mt-0.5">
                          Clique em "+ Adicionar Pacote" para começar.
                        </p>
                      </div>
                    )}

                    {packages.map((pkg, idx) => (
                      <div
                        key={pkg._key}
                        className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-xl px-4 py-3"
                      >
                        <div>
                          <p className="text-sm font-medium text-gray-800">
                            Pacote {idx + 1}
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {pkg.weight_kg} kg · {pkg.height_cm}×{pkg.width_cm}×
                            {pkg.length_cm} cm
                            {pkg.description ? ` · ${pkg.description}` : ""}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              const { _key: _ignored, ...draftFields } = pkg;
                              setPackageDraft(draftFields);
                              setPackageDraftErrors({});
                              setEditingPackageIndex(idx);
                              setShowPackageModal(true);
                            }}
                            className="text-xs px-2.5 py-1 border border-gray-200 text-gray-600 rounded-lg hover:bg-white transition cursor-pointer"
                          >
                            Editar
                          </button>
                          <button
                            type="button"
                            disabled={packages.length <= 1}
                            onClick={() =>
                              setPackages((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                            className="p-1.5 text-gray-400 hover:text-red-500 transition disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                            title="Remover pacote"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Package modal */}
                  {showPackageModal && (
                    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
                      <div
                        className="absolute inset-0 bg-black/40"
                        onClick={() => setShowPackageModal(false)}
                      />
                      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="text-base font-bold text-gray-900">
                            {editingPackageIndex !== null
                              ? "Editar pacote"
                              : "Adicionar pacote"}
                          </h3>
                          <button
                            type="button"
                            onClick={() => setShowPackageModal(false)}
                            className="text-gray-400 hover:text-gray-600 transition cursor-pointer"
                          >
                            <X size={20} />
                          </button>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div className="space-y-1">
                            <label className="block text-xs font-medium text-gray-700">
                              Peso (kg)
                            </label>
                            <input
                              type="number"
                              value={packageDraft.weight_kg}
                              onChange={(e) => {
                                setPackageDraft((prev) => ({
                                  ...prev,
                                  weight_kg: e.target.value,
                                }));
                                if (packageDraftErrors.weight_kg)
                                  setPackageDraftErrors((prev) => {
                                    const n = { ...prev };
                                    delete n.weight_kg;
                                    return n;
                                  });
                              }}
                              min="0.01"
                              step="0.01"
                              placeholder="0.00"
                              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                            />
                            {packageDraftErrors.weight_kg && (
                              <p className="text-xs text-red-500">
                                {packageDraftErrors.weight_kg}
                              </p>
                            )}
                          </div>
                          <div className="space-y-1">
                            <label className="block text-xs font-medium text-gray-700">
                              Altura (cm)
                            </label>
                            <input
                              type="number"
                              value={packageDraft.height_cm}
                              onChange={(e) => {
                                setPackageDraft((prev) => ({
                                  ...prev,
                                  height_cm: e.target.value,
                                }));
                                if (packageDraftErrors.height_cm)
                                  setPackageDraftErrors((prev) => {
                                    const n = { ...prev };
                                    delete n.height_cm;
                                    return n;
                                  });
                              }}
                              min="0.1"
                              step="0.1"
                              placeholder="0.0"
                              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                            />
                            {packageDraftErrors.height_cm && (
                              <p className="text-xs text-red-500">
                                {packageDraftErrors.height_cm}
                              </p>
                            )}
                          </div>
                          <div className="space-y-1">
                            <label className="block text-xs font-medium text-gray-700">
                              Largura (cm)
                            </label>
                            <input
                              type="number"
                              value={packageDraft.width_cm}
                              onChange={(e) => {
                                setPackageDraft((prev) => ({
                                  ...prev,
                                  width_cm: e.target.value,
                                }));
                                if (packageDraftErrors.width_cm)
                                  setPackageDraftErrors((prev) => {
                                    const n = { ...prev };
                                    delete n.width_cm;
                                    return n;
                                  });
                              }}
                              min="0.1"
                              step="0.1"
                              placeholder="0.0"
                              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                            />
                            {packageDraftErrors.width_cm && (
                              <p className="text-xs text-red-500">
                                {packageDraftErrors.width_cm}
                              </p>
                            )}
                          </div>
                          <div className="space-y-1">
                            <label className="block text-xs font-medium text-gray-700">
                              Comprimento (cm)
                            </label>
                            <input
                              type="number"
                              value={packageDraft.length_cm}
                              onChange={(e) => {
                                setPackageDraft((prev) => ({
                                  ...prev,
                                  length_cm: e.target.value,
                                }));
                                if (packageDraftErrors.length_cm)
                                  setPackageDraftErrors((prev) => {
                                    const n = { ...prev };
                                    delete n.length_cm;
                                    return n;
                                  });
                              }}
                              min="0.1"
                              step="0.1"
                              placeholder="0.0"
                              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                            />
                            {packageDraftErrors.length_cm && (
                              <p className="text-xs text-red-500">
                                {packageDraftErrors.length_cm}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="space-y-1">
                          <label className="block text-xs font-medium text-gray-700">
                            Descrição{" "}
                            <span className="text-gray-400 font-normal">
                              (opcional)
                            </span>
                          </label>
                          <input
                            type="text"
                            value={packageDraft.description || ""}
                            onChange={(e) =>
                              setPackageDraft((prev) => ({
                                ...prev,
                                description: e.target.value,
                              }))
                            }
                            maxLength={100}
                            placeholder="Ex: Caixa com espuma protetora"
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition"
                          />
                        </div>

                        <div className="flex gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => setShowPackageModal(false)}
                            className="flex-1 px-4 py-2.5 border border-gray-200 text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 transition cursor-pointer"
                          >
                            Cancelar
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              const errs =
                                validatePackageDraftHelper(packageDraft);
                              if (Object.keys(errs).length > 0) {
                                setPackageDraftErrors(errs);
                                return;
                              }
                              if (editingPackageIndex !== null) {
                                setPackages((prev) =>
                                  prev.map((p, i) =>
                                    i === editingPackageIndex
                                      ? { ...packageDraft, _key: p._key }
                                      : p,
                                  ),
                                );
                              } else {
                                setPackages((prev) => [
                                  ...prev,
                                  {
                                    ...packageDraft,
                                    _key: crypto.randomUUID(),
                                  },
                                ]);
                              }
                              if (errors.packages) {
                                setErrors((prev) => {
                                  const n = { ...prev };
                                  delete n.packages;
                                  return n;
                                });
                              }
                              setShowPackageModal(false);
                            }}
                            className="flex-1 px-4 py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 transition cursor-pointer"
                          >
                            {editingPackageIndex !== null
                              ? "Salvar"
                              : "Adicionar"}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
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
                    <div
                      className={`w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3 transition-colors ${isDragging ? "bg-blue-100" : "bg-gray-100"}`}
                    >
                      <ImagePlus
                        size={22}
                        className={
                          isDragging ? "text-blue-900" : "text-gray-400"
                        }
                      />
                    </div>
                    <p className="text-sm font-semibold text-gray-700">
                      {isDragging
                        ? "Solte as imagens aqui"
                        : "Clique para selecionar ou arraste"}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      JPEG, PNG ou WebP · Máx{" "}
                      {IMAGE_UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB por imagem
                    </p>
                  </label>

                  {uploadError && (
                    <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-start gap-2">
                      <AlertCircle
                        size={16}
                        className="text-red-500 shrink-0 mt-0.5"
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

                  {pendingImages.length === 0 &&
                    existingImages.length === 0 && (
                      <p className="text-sm text-gray-400 text-center py-2">
                        Nenhuma imagem selecionada. As imagens são opcionais,
                        mas aumentam as chances de venda.
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
                className="flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-900 text-white rounded-xl text-sm font-semibold hover:bg-blue-800 active:bg-blue-950 transition disabled:opacity-60 cursor-pointer ml-auto min-w-32.5"
              >
                {submitting || uploading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>{uploading ? "Enviando…" : "Aguarde…"}</span>
                  </>
                ) : isLastStep ? (
                  <>
                    <CheckCircle size={16} />
                    <span>
                      {isEditMode ? "Salvar alterações" : "Publicar Anúncio"}
                    </span>
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
