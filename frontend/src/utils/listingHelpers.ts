import type { FormData } from "@/types/product";

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
 * Steps: 1=Product, 2=Title, 3=Description, 4=Brand&Condition, 5=Price&Qty, 6=Package, 7=Address, 8=Images
 * Returns a map of field names to error messages.
 */
export function validateStep(
  step: number,
  formData: FormData,
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
      if (formData.title.length > 150)
        errors.title = "Máximo 150 caracteres";
      break;
    case 3: // Description
      if (!formData.description.trim())
        errors.description = "Descrição é obrigatória";
      if (formData.description.length > 255)
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
    case 6: // Package dimensions
      if (!formData.weight_kg || Number(formData.weight_kg) <= 0)
        errors.weight_kg = "Peso inválido";
      if (!formData.height_cm || Number(formData.height_cm) <= 0)
        errors.height_cm = "Altura inválida";
      if (!formData.width_cm || Number(formData.width_cm) <= 0)
        errors.width_cm = "Largura inválida";
      if (!formData.length_cm || Number(formData.length_cm) <= 0)
        errors.length_cm = "Comprimento inválido";
      break;
    case 7: // Address
      if (!formData.address_zipcode || formData.address_zipcode.replace(/\D/g, "").length !== 8)
        errors.address_zipcode = "CEP inválido";
      if (!formData.address_neighborhood?.trim())
        errors.address_neighborhood = "Bairro é obrigatório";
      if (!formData.address_city?.trim())
        errors.address_city = "Cidade é obrigatória";
      if (!formData.address_state?.trim())
        errors.address_state = "Estado é obrigatório";
      if (!formData.address_number?.trim())
        errors.address_number = "Número é obrigatório";
      break;
    case 8: // Images - optional, no validation required
      break;
  }

  return errors;
}

/**
 * Builds the listing request data from form data.
 * Returns packages as an array per the new API contract.
 */
export function buildListingData(formData: FormData) {
  const pkg: { weight_kg: string; height_cm: string; width_cm: string; length_cm: string; description?: string } = {
    weight_kg: formatDecimal(formData.weight_kg),
    height_cm: formatDecimal(formData.height_cm),
    width_cm: formatDecimal(formData.width_cm),
    length_cm: formatDecimal(formData.length_cm),
  };
  if (formData.package_description?.trim()) {
    pkg.description = formData.package_description.trim();
  }

  return {
    product: Number(formData.product),
    title: formData.title.trim(),
    brand: Number(formData.brand),
    condition: Number(formData.condition),
    description: formData.description.trim(),
    price: formatDecimal(formData.price),
    quantity: Number(formData.quantity) || 1,
    packages: [pkg],
  };
}
