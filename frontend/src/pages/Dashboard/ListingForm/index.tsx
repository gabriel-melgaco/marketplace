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
  MapPin,
} from "lucide-react";
import { productService } from "@/services/productService";
import { storageService, IMAGE_UPLOAD_LIMITS } from "@/services/storageService";
import { listingImageService } from "@/services/listingImageService";
import api from "@/api/axios";
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
import {
  validateStep as validateStepHelper,
  formatDecimal,
  buildListingData as buildListingDataHelper,
} from "@/utils/listingHelpers";
import Swal from "sweetalert2";

interface ShippingAddress {
  id: number;
  address_type: string;
  nickname: string;
  city: string;
  state: string;
  is_default: boolean;
  is_shipping_address: boolean;
}

const MAX_IMAGES = 10;

const TOTAL_STEPS = 8;

const FIELD_TO_STEP: Record<string, number> = {
  product: 2,
  title: 3,
  brand: 6,
  condition: 6,
  description: 4,
  price: 5,
  quantity: 5,
  weight_kg: 7,
  height_cm: 7,
  width_cm: 7,
  length_cm: 7,
  shipping_address: 8,
};

const STEP_NAMES: Record<number, string> = {
  1: "Imagens",
  2: "Produto",
  3: "Título",
  4: "Descrição",
  5: "Preço",
  6: "Marca e Condição",
  7: "Dimensões",
  8: "Localização",
};

const FIELD_LABELS: Record<string, string> = {
  product: "Produto",
  title: "Título",
  brand: "Marca",
  condition: "Condição",
  description: "Descrição",
  price: "Preço",
  quantity: "Quantidade",
  weight_kg: "Peso (kg)",
  height_cm: "Altura (cm)",
  width_cm: "Largura (cm)",
  length_cm: "Comprimento (cm)",
  shipping_address: "Endereço de envio",
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
  const [productsPage, setProductsPage] = useState(1);
  const [hasMoreProducts, setHasMoreProducts] = useState(false);
  const [loadingMoreProducts, setLoadingMoreProducts] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<ProductListItem | null>(null);
  const [searchingProducts, setSearchingProducts] = useState(false);
  const [searchAbortController, setSearchAbortController] = useState<AbortController | null>(null);
  const draftProductRestoredRef = useRef(false);

  // Draft timing refs — prevent auto-save from overwriting the real draft step
  // before the user has dismissed the Draft Notice.
  const draftStepRef = useRef<number>(1);
  const draftJustLoadedRef = useRef(false);

  const [shippingAddresses, setShippingAddresses] = useState<ShippingAddress[]>([]);
  const [loadingAddresses, setLoadingAddresses] = useState(false);
  const [addressRefreshKey, setAddressRefreshKey] = useState(0);

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

  // Load draft from localStorage (runs once).
  // currentStep intentionally stays at 1 so the Draft Notice can show.
  // The user clicks "Continuar do passo X" to jump to the saved step.
  // draftJustLoadedRef prevents the auto-save effect from overwriting the real
  // draft step before the user has had a chance to act on the notice.
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
        setUploadedImageUrls(draft.uploadedImageUrls || []);
        // Don't restore currentStep here; the Draft Notice handles navigation
      }
    } catch (err) {
      console.error("Error loading draft:", err);
      localStorage.removeItem(draftKey);
    }
  }, [draftKey, isEditMode]);

  // Restore selectedProduct from draft once allProducts loads
  useEffect(() => {
    if (isEditMode || draftProductRestoredRef.current || allProducts.length === 0) return;

    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) {
        const draft: DraftData = JSON.parse(saved);
        if (draft.formData.product) {
          const product = allProducts.find(p => p.id === Number(draft.formData.product));
          if (product) {
            setSelectedProduct(product);
          }
          draftProductRestoredRef.current = true;
        }
      }
    } catch {
      // Draft already handled above
    }
  }, [allProducts, draftKey, isEditMode]);

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

  // Auto-save draft when data changes.
  // Skip saving while draftJustLoadedRef is true — this prevents the effect
  // from firing immediately after draft restoration and overwriting the real
  // saved step with the current step (which is still 1 at that point).
  useEffect(() => {
    if (!isEditMode && currentStep > 0 && !draftJustLoadedRef.current) {
      saveDraft();
    }
  }, [
    currentStep,
    formData,
    uploadedImageUrls,
    saveDraft,
    isEditMode,
  ]);

  // Discard draft with confirmation
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

    // User has explicitly acted — allow auto-save from this point forward
    draftJustLoadedRef.current = false;
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

  // Fetch the authenticated user's addresses.
  // Uses the general /addresses/ endpoint (paginated) so ALL user addresses are available,
  // not just shipping-specific ones.
  // Auto-selects the default address when no address is already chosen in formData.
  // This runs once on mount — addresses are stable for the session lifetime.
  useEffect(() => {
    async function loadShippingAddresses() {
      setLoadingAddresses(true);
      try {
        const response = await api.get<{ results: ShippingAddress[] }>("/logistics/addresses/");
        const allAddresses = response.data.results ?? [];
        // Only show addresses marked as shipping — the backend requires this for listings
        const addresses = allAddresses.filter((a) => a.is_shipping_address);
        setShippingAddresses(addresses);

        // Auto-select an address:
        // - On refresh (addressRefreshKey > 0): select the newest (last) address
        // - On initial load: select the default address if no choice yet
        setFormData((prev) => {
          if (addressRefreshKey > 0 && addresses.length > 0) {
            const newest = addresses[addresses.length - 1];
            return { ...prev, shipping_address: String(newest.id) };
          }
          // Validate that the draft's saved address still exists in the database
          if (prev.shipping_address) {
            const stillExists = addresses.some(
              (a) => a.id === Number(prev.shipping_address),
            );
            if (stillExists) return prev;
            // Address was deleted — clear the stale selection
          }
          const defaultAddr = addresses.find((a) => a.is_default);
          if (defaultAddr) {
            return { ...prev, shipping_address: String(defaultAddr.id) };
          }
          return { ...prev, shipping_address: "" };
        });
      } catch (err) {
        console.error("Erro ao carregar endereços de envio:", err);
      } finally {
        setLoadingAddresses(false);
      }
    }
    loadShippingAddresses();
  }, [addressRefreshKey]);

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
          shipping_address: listing.seller_shipping_address
            ? String(listing.seller_shipping_address.id)
            : "",
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

  // Track pending images in a ref for cleanup on unmount only
  const pendingImagesRef = useRef(pendingImages);
  pendingImagesRef.current = pendingImages;

  useEffect(() => {
    return () => {
      pendingImagesRef.current.forEach((img) => {
        URL.revokeObjectURL(img.previewUrl);
      });
    };
  }, []);

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
          const response = await productService.getProducts({ search: term.trim() });
          // Only update if this request wasn't aborted
          if (!controller.signal.aborted) {
            setProductResults(response.results);
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

  // Step-specific validation (delegates to pure helper)
  const validateStep = (step: number): boolean => {
    const newErrors = validateStepHelper(step, formData);
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
  // Returns the newly uploaded URLs so callers avoid stale closure issues
  const uploadImagesToS3 = useCallback(async (): Promise<UploadedImageUrl[]> => {
    if (pendingImages.length === 0) return [];

    setUploading(true);
    setUploadError(null);
    setUploadProgress({ current: 0, total: pendingImages.length });

    const newUploadedUrls: UploadedImageUrl[] = [];

    try {
      for (let i = 0; i < pendingImages.length; i++) {
        const img = pendingImages[i];
        setUploadProgress({ current: i + 1, total: pendingImages.length });

        // Step 1: Get presigned URL
        const { upload_url, file_url, object_name } =
          await storageService.getPresignedUrl(img.file.name, img.file.type);

        // Step 2: Upload to S3
        await storageService.uploadToS3(upload_url, img.file);

        newUploadedUrls.push({
          url: file_url,
          objectName: object_name,
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

      return newUploadedUrls;
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

      // Validate all images have required fields before linking
      const invalidImages = uploadedImageUrls.filter(
        (img) => !img.url || !img.objectName?.trim(),
      );
      if (invalidImages.length > 0) {
        throw new Error(
          `${invalidImages.length} imagem(ns) sem dados válidos de upload. Tente enviar novamente.`,
        );
      }

      try {
        for (const img of uploadedImageUrls) {
          await listingImageService.addImage(listingId, {
            image_url: img.url,
            object_name: img.objectName,
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

  const buildListingData = useCallback(
    () => buildListingDataHelper(formData),
    [formData],
  );

  // Handle "Continuar" button (Step 1-7)
  // Images are intentionally kept as pendingImages here and only uploaded
  // at final submit, after the listing has been created.
  const handleContinue = async () => {
    if (!validateStep(currentStep)) return;

    setCurrentStep((prev) => Math.min(prev + 1, TOTAL_STEPS));
    setErrors({});
    setUploadError(null);
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
    setUploadError(null);
  };

  // Handle final submit (Step 8 - "Publicar Anúncio")
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Only allow submission from the last step.
    // This prevents accidental form submission when pressing Enter
    // in input fields on earlier steps.
    if (currentStep < TOTAL_STEPS) {
      handleContinue();
      return;
    }

    // Validate ALL steps before hitting the API.
    // This catches any field that may have been left invalid on a previous step
    // so the user is navigated directly to the offending step instead of seeing
    // a generic error after a round-trip to the server.
    const allErrors: Record<string, string> = {};
    for (let step = 1; step <= TOTAL_STEPS; step++) {
      const stepErrors = validateStepHelper(step, formData);
      Object.assign(allErrors, stepErrors);
    }
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      // Navigate to the lowest step number that has an error
      const targetStep = Object.keys(allErrors).reduce((lowest, field) => {
        const step = FIELD_TO_STEP[field] ?? TOTAL_STEPS;
        return step < lowest ? step : lowest;
      }, TOTAL_STEPS);
      setCurrentStep(targetStep);
      return;
    }

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
            const newUrls = await uploadImagesToS3();
            // Link new images using returned array (not stale state)
            for (const img of newUrls) {
              await listingImageService.addImage(Number(id), {
                image_url: img.url,
                object_name: img.objectName,
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
        // Create mode — strict order:
        // STEP 1: create listing → get listing_id
        // STEP 2: per image: presigned URL → upload → associate
        // STEP 3: navigate

        const createData: CreateListingRequest = buildListingData();

        // STEP 1: Create the listing. Abort entirely on failure.
        const createResponse = await productService.createListing(createData);

        // The create endpoint may not return the listing id in the response.
        // If missing, fetch the user's latest listing to obtain it.
        let listingId: number | undefined = createResponse.id;
        if (!listingId) {
          const myListings = await productService.getMyListings();
          if (myListings.results.length > 0) {
            listingId = myListings.results[0].id;
          }
        }

        if (!listingId) {
          throw new Error("Não foi possível obter o ID do anúncio criado.");
        }

        // STEP 2a: For each pending image (not yet uploaded):
        //   a) request presigned URL
        //   b) upload file to MinIO
        //   c) associate image to the listing
        // This guarantees no image is uploaded before the listing exists
        // and no orphan objects are left in MinIO on listing-creation failure.
        if (pendingImages.length > 0) {
          setUploading(true);
          setUploadProgress({ current: 0, total: pendingImages.length });
          try {
            for (let i = 0; i < pendingImages.length; i++) {
              const img = pendingImages[i];
              setUploadProgress({ current: i + 1, total: pendingImages.length });

              // a) Presigned URL
              const { upload_url, file_url, object_name } =
                await storageService.getPresignedUrl(img.file.name, img.file.type);

              // b) Upload
              await storageService.uploadToS3(upload_url, img.file);

              // c) Associate
              await listingImageService.addImage(listingId, {
                image_url: file_url,
                object_name,
                is_primary: img.isPrimary,
                order: i,
              });
            }
          } catch (uploadErr) {
            console.error("Upload/associate error:", uploadErr);
            setUploadError(
              "Anúncio criado, mas houve erro ao enviar algumas imagens. Você pode adicioná-las editando o anúncio.",
            );
            localStorage.removeItem(draftKey);
            setTimeout(() => navigate(`/productdetail/${listingId}`), 3000);
            return;
          } finally {
            setUploading(false);
            setUploadProgress({ current: 0, total: 0 });
          }
        }

        // STEP 2b: Associate any images that were already uploaded in a previous
        // session (e.g., restored from an older draft). These have a valid
        // file_url and object_name but were never linked to a listing.
        if (uploadedImageUrls.length > 0) {
          try {
            await linkImagesToListing(listingId);
          } catch (linkErr) {
            console.error("Link error:", linkErr);
            setUploadError(
              "Anúncio criado, mas houve erro ao vincular algumas imagens. Você pode adicioná-las editando o anúncio.",
            );
            localStorage.removeItem(draftKey);
            setTimeout(() => navigate(`/productdetail/${listingId}`), 3000);
            return;
          }
        }

        // STEP 3: Clear draft and navigate to the new listing
        localStorage.removeItem(draftKey);
        navigate(`/productdetail/${listingId}`);
      }
    } catch (err: any) {
      console.error("Erro ao salvar anúncio:", err);

      // Parse validation errors returned by the API.
      // DRF can return: field arrays, "detail" string, or "non_field_errors" array.
      if (err.response?.data) {
        console.error("API validation errors:", err.response.data);
        const apiErrors = err.response.data;

        // Handle "detail" string (auth errors, 404, etc.)
        if (typeof apiErrors.detail === "string") {
          setUploadError(apiErrors.detail);
          return;
        }

        // Handle "non_field_errors" (global validation errors)
        if (Array.isArray(apiErrors.non_field_errors) && apiErrors.non_field_errors.length > 0) {
          setUploadError(apiErrors.non_field_errors[0]);
          return;
        }

        // Parse field-level errors and navigate to the correct step
        const newErrors: Record<string, string> = {};
        Object.keys(apiErrors).forEach((field) => {
          const messages = apiErrors[field];
          if (Array.isArray(messages) && messages.length > 0) {
            newErrors[field] = messages[0];
          } else if (typeof messages === "string") {
            newErrors[field] = messages;
          }
        });

        if (Object.keys(newErrors).length > 0) {
          setErrors(newErrors);
          // Navigate to the lowest step number that has an error
          const targetStep = Object.keys(newErrors).reduce((lowest, field) => {
            const step = FIELD_TO_STEP[field] ?? TOTAL_STEPS;
            return step < lowest ? step : lowest;
          }, TOTAL_STEPS);
          setCurrentStep(targetStep);
          return;
        }
      }

      setUploadError("Erro ao salvar anúncio. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  };

  // Opens a SweetAlert2 modal with a full address creation form.
  // On success the new address is appended to shippingAddresses and
  // auto-selected in formData.shipping_address.
  const handleCreateAddress = useCallback(async () => {
    const { value: confirmed, isConfirmed } = await Swal.fire({
      title: "Cadastrar Novo Endereço",
      width: 600,
      html: `
        <div style="text-align:left; font-family: inherit;">
          <div style="display:grid; gap:12px;">

            <!-- CEP row -->
            <div>
              <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                CEP <span style="color:#ef4444;">*</span>
              </label>
              <div style="display:flex; gap:8px;">
                <input
                  id="swal-zipcode"
                  type="text"
                  maxlength="9"
                  placeholder="00000-000"
                  style="flex:1; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none;"
                />
                <button
                  id="swal-cep-btn"
                  type="button"
                  style="padding:8px 14px; background:#1e3a8a; color:#fff; border:none; border-radius:8px; font-size:13px; cursor:pointer; white-space:nowrap;"
                >
                  Buscar CEP
                </button>
              </div>
              <p id="swal-cep-error" style="display:none; font-size:12px; color:#ef4444; margin-top:4px;"></p>
            </div>

            <!-- Street + Number -->
            <div style="display:grid; grid-template-columns:1fr auto; gap:8px;">
              <div>
                <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                  Rua / Logradouro <span style="color:#ef4444;">*</span>
                </label>
                <input
                  id="swal-street"
                  type="text"
                  placeholder="Rua das Flores"
                  style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
                />
              </div>
              <div style="min-width:90px;">
                <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                  Número <span style="color:#ef4444;">*</span>
                </label>
                <input
                  id="swal-number"
                  type="text"
                  placeholder="123"
                  style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
                />
              </div>
            </div>

            <!-- Complement -->
            <div>
              <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                Complemento
              </label>
              <input
                id="swal-complement"
                type="text"
                placeholder="Apto 42, Bloco B (opcional)"
                style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
              />
            </div>

            <!-- Neighborhood -->
            <div>
              <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                Bairro <span style="color:#ef4444;">*</span>
              </label>
              <input
                id="swal-neighborhood"
                type="text"
                placeholder="Centro"
                style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
              />
            </div>

            <!-- City + State -->
            <div style="display:grid; grid-template-columns:1fr 80px; gap:8px;">
              <div>
                <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                  Cidade <span style="color:#ef4444;">*</span>
                </label>
                <input
                  id="swal-city"
                  type="text"
                  placeholder="São Paulo"
                  style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
                />
              </div>
              <div>
                <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                  Estado <span style="color:#ef4444;">*</span>
                </label>
                <input
                  id="swal-state"
                  type="text"
                  maxlength="2"
                  placeholder="SP"
                  style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box; text-transform:uppercase;"
                />
              </div>
            </div>

            <!-- Nickname -->
            <div>
              <div>
                <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                  Apelido
                </label>
                <input
                  id="swal-nickname"
                  type="text"
                  placeholder="Ex: Casa, Trabalho"
                  style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
                />
              </div>
            </div>

            <!-- Recipient Name -->
            <div>
              <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                Nome do responsável <span style="color:#ef4444;">*</span>
              </label>
              <input
                id="swal-recipient-name"
                type="text"
                placeholder="Nome completo"
                style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
              />
            </div>

            <!-- Recipient Phone -->
            <div>
              <label style="display:block; font-size:13px; font-weight:600; color:#374151; margin-bottom:4px;">
                Telefone de contato <span style="color:#ef4444;">*</span>
              </label>
              <input
                id="swal-recipient-phone"
                type="text"
                placeholder="(11) 99999-9999"
                style="width:100%; padding:8px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:14px; outline:none; box-sizing:border-box;"
              />
            </div>

            <!-- Checkbox -->
            <div style="padding-top:4px;">
              <label style="display:flex; align-items:center; gap:8px; font-size:14px; color:#374151; cursor:pointer;">
                <input
                  id="swal-is-default"
                  type="checkbox"
                  style="width:16px; height:16px; accent-color:#1e3a8a; cursor:pointer;"
                />
                Definir como endereço padrão
              </label>
            </div>

            <div style="padding:8px 12px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;">
              <p style="font-size:12px; color:#1e40af; margin:0;">
                Este endereço será registrado como <strong>Endereço de Envio do Vendedor</strong>, obrigatório para publicar anúncios.
              </p>
            </div>

          </div>
        </div>
      `,
      confirmButtonText: "Cadastrar",
      confirmButtonColor: "#1e3a8a",
      cancelButtonText: "Cancelar",
      cancelButtonColor: "#6b7280",
      showCancelButton: true,
      focusConfirm: false,
      didOpen: () => {
        // CEP input masking: format as 00000-000 as user types
        const zipcodeInput = document.getElementById("swal-zipcode") as HTMLInputElement | null;
        if (zipcodeInput) {
          zipcodeInput.addEventListener("input", () => {
            let val = zipcodeInput.value.replace(/\D/g, "");
            if (val.length > 8) val = val.slice(0, 8);
            if (val.length > 5) {
              val = val.slice(0, 5) + "-" + val.slice(5);
            }
            zipcodeInput.value = val;
          });
        }

        // CEP lookup button handler
        const cepBtn = document.getElementById("swal-cep-btn") as HTMLButtonElement | null;
        const cepError = document.getElementById("swal-cep-error") as HTMLParagraphElement | null;

        if (cepBtn) {
          cepBtn.addEventListener("click", async () => {
            const rawZipcode = zipcodeInput?.value.replace(/\D/g, "") ?? "";
            if (rawZipcode.length !== 8) {
              if (cepError) {
                cepError.textContent = "Informe um CEP com 8 dígitos.";
                cepError.style.display = "block";
              }
              return;
            }
            if (cepError) cepError.style.display = "none";

            cepBtn.disabled = true;
            cepBtn.textContent = "Buscando...";

            try {
              const res = await api.post<{
                zipcode: string;
                street: string;
                neighborhood: string;
                city: string;
                state: string;
              }>("/logistics/cep/lookup/", { zipcode: rawZipcode });

              const { street, neighborhood, city, state } = res.data;

              const setVal = (id: string, val: string) => {
                const el = document.getElementById(id) as HTMLInputElement | null;
                if (el) el.value = val;
              };

              setVal("swal-street", street ?? "");
              setVal("swal-neighborhood", neighborhood ?? "");
              setVal("swal-city", city ?? "");
              setVal("swal-state", (state ?? "").toUpperCase());
            } catch {
              if (cepError) {
                cepError.textContent = "CEP não encontrado. Preencha os campos manualmente.";
                cepError.style.display = "block";
              }
            } finally {
              cepBtn.disabled = false;
              cepBtn.textContent = "Buscar CEP";
            }
          });
        }
      },
      preConfirm: async () => {
        const getVal = (id: string): string => {
          const el = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
          return el ? el.value.trim() : "";
        };
        const getChecked = (id: string): boolean => {
          const el = document.getElementById(id) as HTMLInputElement | null;
          return el ? el.checked : false;
        };

        const zipcode = getVal("swal-zipcode").replace(/\D/g, "");
        const street = getVal("swal-street");
        const number = getVal("swal-number");
        const complement = getVal("swal-complement");
        const neighborhood = getVal("swal-neighborhood");
        const city = getVal("swal-city");
        const state = getVal("swal-state").toUpperCase();
        const nickname = getVal("swal-nickname");
        const recipient_name = getVal("swal-recipient-name");
        const recipient_phone = getVal("swal-recipient-phone");
        const is_default = getChecked("swal-is-default");

        const missing: string[] = [];
        if (!zipcode || zipcode.length !== 8) missing.push("CEP (8 dígitos)");
        if (!street) missing.push("Rua / Logradouro");
        if (!number) missing.push("Número");
        if (!neighborhood) missing.push("Bairro");
        if (!city) missing.push("Cidade");
        if (!state) missing.push("Estado");
        if (!recipient_name) missing.push("Nome do responsável");
        if (!recipient_phone) missing.push("Telefone de contato");

        if (missing.length > 0) {
          Swal.showValidationMessage(
            `Preencha os campos obrigatórios: ${missing.join(", ")}.`,
          );
          return false;
        }

        try {
          const response = await api.post<ShippingAddress>("/logistics/addresses/", {
            zipcode,
            street,
            number,
            complement: complement || undefined,
            neighborhood,
            city,
            state,
            address_type: "shipping",
            nickname: nickname || undefined,
            recipient_name,
            recipient_phone,
            is_default,
          });
          return response.data;
        } catch (err: any) {
          const detail =
            err?.response?.data?.detail ??
            err?.response?.data?.non_field_errors?.[0] ??
            "Erro ao cadastrar endereço. Verifique os dados e tente novamente.";
          Swal.showValidationMessage(String(detail));
          return false;
        }
      },
    });

    if (!isConfirmed || !confirmed) return;

    // The POST /addresses/ response (AddressCreate schema) does NOT include `id`.
    // Trigger useEffect re-fetch so the new address appears in the dropdown
    setAddressRefreshKey((k) => k + 1);

    await Swal.fire({
      toast: true,
      position: "top-end",
      icon: "success",
      title: "Endereço cadastrado com sucesso!",
      showConfirmButton: false,
      timer: 3000,
      timerProgressBar: true,
    });
  }, [setFormData, setShippingAddresses]);

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
    { step: 8, title: "Local", icon: MapPin },
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
        {!isEditMode && hasDraft && currentStep === 1 && (() => {
          // Read from the ref — guaranteed to hold the original draft step because
          // we stored it at load time and the auto-save guard keeps it intact.
          const draftStep = draftStepRef.current;
          const draftStepName = stepConfig.find(s => s.step === draftStep)?.title ?? `Passo ${draftStep}`;

          return (
            <div className="bg-blue-800 rounded-xl p-4 mb-6 border border-blue-700">
              <div className="flex flex-col gap-3">
                <div>
                  <p className="text-white font-medium mb-1">
                    Rascunho encontrado
                  </p>
                  <p className="text-blue-200 text-sm">
                    Você parou no passo <strong className="text-white">{draftStep} de {TOTAL_STEPS}</strong> ({draftStepName}).
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      // User chose to continue — lift the auto-save guard and
                      // jump to the step they were on.
                      draftJustLoadedRef.current = false;
                      setHasDraft(false);
                      setCurrentStep(draftStep);
                    }}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-white text-blue-900 rounded-lg text-sm font-semibold hover:bg-gray-100 transition-all"
                  >
                    <ArrowRight size={14} />
                    Continuar do passo {draftStep}
                  </button>
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
            </div>
          );
        })()}

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
          <div className="flex items-start justify-between">
            {stepConfig.map(({ step, title, icon: Icon }) => (
              <div key={step} className="flex flex-col items-center gap-1 w-0 flex-1">
                <div
                  className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center shrink-0 transition-all ${
                    step < currentStep
                      ? "bg-green-500 text-white"
                      : step === currentStep
                        ? "bg-blue-800 text-white"
                        : "bg-gray-200 text-gray-400"
                  }`}
                >
                  {step < currentStep ? (
                    <CheckCircle size={16} className="sm:w-5 sm:h-5" />
                  ) : (
                    <Icon size={16} className="sm:w-5 sm:h-5" />
                  )}
                </div>
                <span
                  className={`text-[9px] sm:text-xs font-medium text-center leading-tight ${
                    step === currentStep
                      ? "text-blue-800"
                      : step < currentStep
                        ? "text-green-600"
                        : "text-gray-400"
                  }`}
                >
                  <span className="hidden sm:inline">{title}</span>
                  <span className="sm:hidden">{step}</span>
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
                        {hasMoreProducts && (
                          <button
                            type="button"
                            onClick={loadMoreProducts}
                            disabled={loadingMoreProducts}
                            className="w-full text-center px-3 py-2.5 text-sm font-medium text-blue-800 hover:bg-blue-50 transition-colors disabled:opacity-50"
                          >
                            {loadingMoreProducts ? (
                              <span className="flex items-center justify-center gap-2">
                                <Loader2 size={14} className="animate-spin" />
                                Carregando...
                              </span>
                            ) : (
                              "Carregar mais produtos"
                            )}
                          </button>
                        )}
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
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                    errors.quantity
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300 bg-white"
                  }`}
                />
                {errors.quantity ? (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.quantity}</p>
                  </div>
                ) : (
                  <p className="text-xs text-gray-500 mt-1">Padrão: 1 unidade</p>
                )}
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

          {/* STEP 8: LOCATION */}
          {currentStep === 8 && (
            <div className="bg-white rounded-xl p-5 sm:p-6 shadow-md space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                  <MapPin size={20} className="text-blue-800" />
                  Localização do Anúncio
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Informe o endereço onde o equipamento está localizado. Este endereço será usado para filtros de localização.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Endereço do anúncio
                </label>
                {loadingAddresses ? (
                  <div className="flex items-center gap-2 py-2 text-sm text-gray-500">
                    <Loader2 size={16} className="animate-spin text-blue-800" />
                    Carregando endereços...
                  </div>
                ) : shippingAddresses.length === 0 ? (
                  <div className="space-y-3">
                    <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                      <p className="text-xs text-yellow-800">
                        Você não possui um endereço cadastrado. Cadastre um endereço para continuar.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleCreateAddress}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-800 text-white text-sm font-medium rounded-lg hover:bg-blue-900 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2"
                    >
                      + Cadastrar Novo Endereço
                    </button>
                  </div>
                ) : (
                  <>
                    <select
                      name="shipping_address"
                      value={formData.shipping_address}
                      onChange={handleChange}
                      className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-800 focus:border-transparent transition-colors ${
                        errors.shipping_address
                          ? "border-red-300 bg-red-50"
                          : "border-gray-300 bg-white"
                      }`}
                    >
                      <option value="">Selecione um endereço</option>
                      {shippingAddresses.map((addr) => (
                        <option key={addr.id} value={addr.id}>
                          {addr.nickname
                            ? `${addr.nickname} - ${addr.city}, ${addr.state}`
                            : `${addr.city}, ${addr.state}`}
                          {addr.is_default ? " (padrão)" : ""}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Este é o local onde o equipamento se encontra, não necessariamente o seu endereço pessoal.
                    </p>
                    <button
                      type="button"
                      onClick={handleCreateAddress}
                      className="mt-2 flex items-center gap-2 px-4 py-2 border border-blue-800 text-blue-800 text-sm font-medium rounded-lg hover:bg-blue-50 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-800 focus:ring-offset-2"
                    >
                      + Cadastrar Novo Endereço
                    </button>
                  </>
                )}
                {errors.shipping_address && (
                  <div className="flex items-start gap-1 mt-1">
                    <X size={14} className="text-red-500 shrink-0 mt-0.5" />
                    <p className="text-red-600 text-xs">{errors.shipping_address}</p>
                  </div>
                )}
              </div>

              {formData.shipping_address && (() => {
                const selected = shippingAddresses.find(
                  (a) => a.id === Number(formData.shipping_address),
                );
                if (!selected) return null;
                return (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-sm font-medium text-gray-900">
                      {selected.nickname || "Endereço selecionado"}
                    </p>
                    <p className="text-xs text-gray-600 mt-0.5">
                      {selected.city}, {selected.state}
                    </p>
                  </div>
                );
              })()}
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
