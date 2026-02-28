import { describe, it, expect } from "vitest";
import {
  formatDecimal,
  validateStep,
  buildListingData,
} from "../listingHelpers";
import type { FormData } from "@/types/product";

const EMPTY_FORM: FormData = {
  product: "",
  title: "",
  brand: "",
  condition: "",
  description: "",
  price: "",
  quantity: "",
  weight_kg: "",
  height_cm: "",
  width_cm: "",
  length_cm: "",
  package_description: "",
  // Address fields (step 7)
  address_zipcode: "",
  address_street: "",
  address_number: "",
  address_complement: "",
  address_neighborhood: "",
  address_city: "",
  address_state: "",
};

function formWith(overrides: Partial<FormData>): FormData {
  return { ...EMPTY_FORM, ...overrides };
}

describe("formatDecimal", () => {
  it("formats valid number to 2 decimal places", () => {
    expect(formatDecimal("10")).toBe("10.00");
    expect(formatDecimal("10.5")).toBe("10.50");
    expect(formatDecimal("99.999")).toBe("100.00");
  });

  it("returns '0.00' for empty string", () => {
    expect(formatDecimal("")).toBe("0.00");
  });

  it("returns '0.00' for non-numeric string", () => {
    expect(formatDecimal("abc")).toBe("0.00");
    expect(formatDecimal("not-a-number")).toBe("0.00");
  });

  it("handles zero", () => {
    expect(formatDecimal("0")).toBe("0.00");
    expect(formatDecimal("0.0")).toBe("0.00");
  });

  it("handles negative numbers", () => {
    expect(formatDecimal("-5.5")).toBe("-5.50");
  });

  it("handles very small decimals", () => {
    expect(formatDecimal("0.1")).toBe("0.10");
    expect(formatDecimal("0.01")).toBe("0.01");
    expect(formatDecimal("0.001")).toBe("0.00");
  });
});

describe("validateStep", () => {
  describe("Step 1 - Product", () => {
    it("requires product selection", () => {
      const errors = validateStep(1, EMPTY_FORM);
      expect(errors.product).toBe("Selecione um produto");
    });

    it("rejects product value '0'", () => {
      const errors = validateStep(1, formWith({ product: "0" }));
      expect(errors.product).toBe("Selecione um produto");
    });

    it("rejects negative product value", () => {
      const errors = validateStep(1, formWith({ product: "-1" }));
      expect(errors.product).toBe("Selecione um produto");
    });

    it("accepts valid product ID", () => {
      const errors = validateStep(1, formWith({ product: "42" }));
      expect(errors).toEqual({});
    });
  });

  describe("Step 2 - Title", () => {
    it("requires title", () => {
      const errors = validateStep(2, EMPTY_FORM);
      expect(errors.title).toBe("O título do anúncio é obrigatório");
    });

    it("rejects whitespace-only title", () => {
      const errors = validateStep(2, formWith({ title: "   " }));
      expect(errors.title).toBe("O título do anúncio é obrigatório");
    });

    it("rejects title over 150 characters", () => {
      const errors = validateStep(2, formWith({ title: "A".repeat(151) }));
      expect(errors.title).toBe("Máximo 150 caracteres");
    });

    it("accepts valid title", () => {
      const errors = validateStep(
        2,
        formWith({ title: "Esteira Elétrica Movement R3" }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 3 - Description", () => {
    it("requires description", () => {
      const errors = validateStep(3, EMPTY_FORM);
      expect(errors.description).toBe("Descrição é obrigatória");
    });

    it("rejects description over 255 characters", () => {
      const errors = validateStep(
        3,
        formWith({ description: "A".repeat(256) }),
      );
      expect(errors.description).toBe("Máximo 255 caracteres");
    });

    it("accepts valid description", () => {
      const errors = validateStep(
        3,
        formWith({ description: "Equipamento em ótimo estado" }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 4 - Brand and Condition", () => {
    it("requires both brand and condition", () => {
      const errors = validateStep(4, EMPTY_FORM);
      expect(errors.brand).toBe("Selecione uma marca");
      expect(errors.condition).toBe("Selecione a condição");
    });

    it("accepts valid brand and condition", () => {
      const errors = validateStep(
        4,
        formWith({ brand: "1", condition: "2" }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 5 - Price", () => {
    it("requires price", () => {
      const errors = validateStep(5, EMPTY_FORM);
      expect(errors.price).toBe("Preço inválido");
    });

    it("rejects price of 0", () => {
      const errors = validateStep(5, formWith({ price: "0" }));
      expect(errors.price).toBe("Preço inválido");
    });

    it("rejects negative price", () => {
      const errors = validateStep(5, formWith({ price: "-10" }));
      expect(errors.price).toBe("Preço inválido");
    });

    it("accepts valid price", () => {
      const errors = validateStep(5, formWith({ price: "1500.00" }));
      expect(errors).toEqual({});
    });
  });

  describe("Step 6 - Package Dimensions", () => {
    it("requires all dimension fields", () => {
      const errors = validateStep(6, EMPTY_FORM);
      expect(errors.weight_kg).toBe("Peso inválido");
      expect(errors.height_cm).toBe("Altura inválida");
      expect(errors.width_cm).toBe("Largura inválida");
      expect(errors.length_cm).toBe("Comprimento inválido");
    });

    it("rejects zero values", () => {
      const errors = validateStep(
        6,
        formWith({
          weight_kg: "0",
          height_cm: "0",
          width_cm: "0",
          length_cm: "0",
        }),
      );
      expect(Object.keys(errors)).toHaveLength(4);
    });

    it("accepts valid dimensions", () => {
      const errors = validateStep(
        6,
        formWith({
          weight_kg: "25.5",
          height_cm: "150",
          width_cm: "80",
          length_cm: "200",
        }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 7 - Address", () => {
    it("requires all mandatory address fields when empty", () => {
      const errors = validateStep(7, EMPTY_FORM);
      expect(errors.address_zipcode).toBeTruthy();
      expect(errors.address_neighborhood).toBeTruthy();
      expect(errors.address_city).toBeTruthy();
      expect(errors.address_state).toBeTruthy();
      expect(errors.address_number).toBeTruthy();
    });

    it("rejects a CEP that has fewer than 8 digits", () => {
      const errors = validateStep(7, formWith({ address_zipcode: "1234567" }));
      expect(errors.address_zipcode).toBe("CEP inválido");
    });

    it("rejects a CEP that has more than 8 digits", () => {
      const errors = validateStep(7, formWith({ address_zipcode: "123456789" }));
      expect(errors.address_zipcode).toBe("CEP inválido");
    });

    it("accepts a formatted CEP (01310-100) by counting only digits", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310-100",
          address_number: "100",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
        }),
      );
      expect(errors.address_zipcode).toBeUndefined();
    });

    it("accepts a bare 8-digit CEP (01310100)", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310100",
          address_number: "100",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
        }),
      );
      expect(errors.address_zipcode).toBeUndefined();
    });

    it("requires address_number", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310100",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
          address_number: "",
        }),
      );
      expect(errors.address_number).toBe("Número é obrigatório");
    });

    it("rejects whitespace-only address_number", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310100",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
          address_number: "   ",
        }),
      );
      expect(errors.address_number).toBe("Número é obrigatório");
    });

    it("does NOT require address_complement (it is optional)", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310100",
          address_number: "100",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
          address_complement: "",
        }),
      );
      expect(errors.address_complement).toBeUndefined();
    });

    it("returns no errors for a fully valid address", () => {
      const errors = validateStep(
        7,
        formWith({
          address_zipcode: "01310100",
          address_street: "Avenida Paulista",
          address_number: "1000",
          address_complement: "Sala 5",
          address_neighborhood: "Bela Vista",
          address_city: "São Paulo",
          address_state: "SP",
          address_recipient_name: "João Silva",
          address_recipient_phone: "11999998888",
        }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 8 - Images", () => {
    it("returns no errors (images are optional)", () => {
      const errors = validateStep(8, EMPTY_FORM);
      expect(errors).toEqual({});
    });
  });
});

describe("buildListingData", () => {
  it("builds correct request data with packages array", () => {
    const form = formWith({
      product: "42",
      title: "  Esteira Movement R3  ",
      brand: "5",
      condition: "2",
      description: "  Em ótimo estado  ",
      price: "1500",
      quantity: "3",
      weight_kg: "25.5",
      height_cm: "150",
      width_cm: "80",
      length_cm: "200",
    });

    const data = buildListingData(form);

    expect(data.product).toBe(42);
    expect(data.title).toBe("Esteira Movement R3");
    expect(data.brand).toBe(5);
    expect(data.condition).toBe(2);
    expect(data.description).toBe("Em ótimo estado");
    expect(data.price).toBe("1500.00");
    expect(data.quantity).toBe(3);
    expect(data.packages).toHaveLength(1);
    expect(data.packages[0].weight_kg).toBe("25.50");
    expect(data.packages[0].height_cm).toBe("150.00");
    expect(data.packages[0].width_cm).toBe("80.00");
    expect(data.packages[0].length_cm).toBe("200.00");
  });

  it("defaults quantity to 1 when empty", () => {
    const data = buildListingData(EMPTY_FORM);
    expect(data.quantity).toBe(1);
  });

  it("does not include shipping_address field", () => {
    const data = buildListingData(EMPTY_FORM);
    expect("shipping_address" in data).toBe(false);
  });

  it("includes package_description in packages when provided", () => {
    const form = formWith({
      weight_kg: "1",
      height_cm: "10",
      width_cm: "10",
      length_cm: "10",
      package_description: "Caixa grande",
    });
    const data = buildListingData(form);
    expect(data.packages[0].description).toBe("Caixa grande");
  });

  it("omits package description field when empty", () => {
    const form = formWith({
      weight_kg: "1",
      height_cm: "10",
      width_cm: "10",
      length_cm: "10",
      package_description: "",
    });
    const data = buildListingData(form);
    expect("description" in data.packages[0]).toBe(false);
  });

  it("trims whitespace from title and description", () => {
    const form = formWith({
      title: "  test  ",
      description: "  desc  ",
    });
    const data = buildListingData(form);
    expect(data.title).toBe("test");
    expect(data.description).toBe("desc");
  });

  it("formats decimals to 2 places in packages", () => {
    const form = formWith({
      price: "10.5",
      weight_kg: "3",
      height_cm: "0.1",
      width_cm: "99.999",
      length_cm: "",
    });
    const data = buildListingData(form);
    expect(data.price).toBe("10.50");
    expect(data.packages[0].weight_kg).toBe("3.00");
    expect(data.packages[0].height_cm).toBe("0.10");
    expect(data.packages[0].width_cm).toBe("100.00");
    expect(data.packages[0].length_cm).toBe("0.00");
  });
});
