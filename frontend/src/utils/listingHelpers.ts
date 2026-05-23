import type { FormData, ListingPackageRequest } from "@/types/product";

/**
 * Formats a decimal string to 2 decimal places.
 * Returns "0.00" for invalid input.
 */
export function formatDecimal(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return "0.00";
  return num.toFixed(2);
}

/**
 * Validates a specific step of the listing form.
 * Steps: 1=Product, 2=Title, 3=Description, 4=Brand&Condition, 5=Price&Qty, 6=Package, 7=Images
 * Returns a map of field names to error messages.
 */
export function validateStep(
  step: number,
  formData: FormData,
  packages?: ListingPackageRequest[],
): Record<string, string> {
  const errors: Record<string, string> = {};

  switch (step) {
    case 1: // Product
      if (
        !formData.product ||
        formData.product.trim() === "" ||
        Number(formData.product) <= 0
      ) {
        errors.product = "Selecione um produto";
      }
      break;
    case 2: // Title
      if (!formData.title.trim())
        errors.title = "O título do anúncio é obrigatório";
      else if (formData.title.length > 150)
        errors.title = "Máximo 150 caracteres";
      break;
    case 3: // Description
      if (!formData.description.trim())
        errors.description = "Descrição é obrigatória";
      else if (formData.description.trim().length < 30)
        errors.description = "Descrição precisa ter pelo menos 30 caracteres";
      else if (formData.description.length > 255)
        errors.description = "Máximo 255 caracteres";
      break;
    case 4: // Brand and Condition
      if (!formData.brand) errors.brand = "Selecione uma marca";
      if (!formData.condition) errors.condition = "Selecione a condição";
      break;
    case 5: // Price and Quantity
      if (!formData.price || Number(formData.price) <= 0)
        errors.price = "Preço inválido";
      break;
    case 6: // Pacotes & Método de Envio
      if (!packages || packages.length === 0) {
        errors.packages = "Adicione pelo menos um pacote";
      }
      break;
    case 7: // Images — optional, no validation required
      break;
  }

  return errors;
}

/**
 * Validates a single package draft before adding/editing.
 * Returns a map of field names to error messages.
 */
export function validatePackageDraft(
  pkg: ListingPackageRequest,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!pkg.weight_kg || Number(pkg.weight_kg) <= 0)
    errors.weight_kg = "Peso inválido";
  if (!pkg.height_cm || Number(pkg.height_cm) <= 0)
    errors.height_cm = "Altura inválida";
  if (!pkg.width_cm || Number(pkg.width_cm) <= 0)
    errors.width_cm = "Largura inválida";
  if (!pkg.length_cm || Number(pkg.length_cm) <= 0)
    errors.length_cm = "Comprimento inválido";
  return errors;
}

/**
 * Builds the listing request data from form data.
 * Returns packages as an array per the new API contract.
 */
export function buildListingData(
  formData: FormData,
  packages: ListingPackageRequest[],
) {
  return {
    product: Number(formData.product),
    title: formData.title.trim(),
    brand: Number(formData.brand),
    condition: Number(formData.condition),
    description: formData.description.trim(),
    price: formatDecimal(formData.price),
    quantity: Number(formData.quantity) || 1,
    packages: packages.map((pkg) => ({
      weight_kg: formatDecimal(pkg.weight_kg),
      height_cm: formatDecimal(pkg.height_cm),
      width_cm: formatDecimal(pkg.width_cm),
      length_cm: formatDecimal(pkg.length_cm),
      ...(pkg.description?.trim()
        ? { description: pkg.description.trim() }
        : {}),
    })),
    shipping_method: formData.shipping_method,
  };
}
