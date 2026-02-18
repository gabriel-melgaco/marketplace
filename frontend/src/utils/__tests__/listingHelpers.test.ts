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
  describe("Step 1 - Images", () => {
    it("returns no errors (images are optional)", () => {
      const errors = validateStep(1, EMPTY_FORM);
      expect(errors).toEqual({});
    });
  });

  describe("Step 2 - Product", () => {
    it("requires product selection", () => {
      const errors = validateStep(2, EMPTY_FORM);
      expect(errors.product).toBe("Selecione um produto");
    });

    it("rejects product value '0'", () => {
      const errors = validateStep(2, formWith({ product: "0" }));
      expect(errors.product).toBe("Selecione um produto");
    });

    it("rejects negative product value", () => {
      const errors = validateStep(2, formWith({ product: "-1" }));
      expect(errors.product).toBe("Selecione um produto");
    });

    it("accepts valid product ID", () => {
      const errors = validateStep(2, formWith({ product: "42" }));
      expect(errors).toEqual({});
    });
  });

  describe("Step 3 - Title", () => {
    it("requires title", () => {
      const errors = validateStep(3, EMPTY_FORM);
      expect(errors.title).toBe("O título do anúncio é obrigatório");
    });

    it("rejects whitespace-only title", () => {
      const errors = validateStep(3, formWith({ title: "   " }));
      expect(errors.title).toBe("O título do anúncio é obrigatório");
    });

    it("rejects title over 150 characters", () => {
      const errors = validateStep(3, formWith({ title: "A".repeat(151) }));
      expect(errors.title).toBe("Máximo 150 caracteres");
    });

    it("accepts valid title", () => {
      const errors = validateStep(
        3,
        formWith({ title: "Esteira Elétrica Movement R3" }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 4 - Description", () => {
    it("requires description", () => {
      const errors = validateStep(4, EMPTY_FORM);
      expect(errors.description).toBe("Descrição é obrigatória");
    });

    it("rejects description over 255 characters", () => {
      const errors = validateStep(
        4,
        formWith({ description: "A".repeat(256) }),
      );
      expect(errors.description).toBe("Máximo 255 caracteres");
    });

    it("accepts valid description", () => {
      const errors = validateStep(
        4,
        formWith({ description: "Equipamento em ótimo estado" }),
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

  describe("Step 6 - Brand and Condition", () => {
    it("requires both brand and condition", () => {
      const errors = validateStep(6, EMPTY_FORM);
      expect(errors.brand).toBe("Selecione uma marca");
      expect(errors.condition).toBe("Selecione a condição");
    });

    it("accepts valid brand and condition", () => {
      const errors = validateStep(
        6,
        formWith({ brand: "1", condition: "2" }),
      );
      expect(errors).toEqual({});
    });
  });

  describe("Step 7 - Dimensions and Weight", () => {
    it("requires all dimension fields", () => {
      const errors = validateStep(7, EMPTY_FORM);
      expect(errors.weight_kg).toBe("Peso inválido");
      expect(errors.height_cm).toBe("Altura inválida");
      expect(errors.width_cm).toBe("Largura inválida");
      expect(errors.length_cm).toBe("Comprimento inválido");
    });

    it("rejects zero values", () => {
      const errors = validateStep(
        7,
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
        7,
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
});

describe("buildListingData", () => {
  it("builds correct request data from form", () => {
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
    expect(data.weight_kg).toBe("25.50");
    expect(data.height_cm).toBe("150.00");
    expect(data.width_cm).toBe("80.00");
    expect(data.length_cm).toBe("200.00");
  });

  it("defaults quantity to 1 when empty", () => {
    const data = buildListingData(EMPTY_FORM);
    expect(data.quantity).toBe(1);
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

  it("formats decimals to 2 places", () => {
    const form = formWith({
      price: "10.5",
      weight_kg: "3",
      height_cm: "0.1",
      width_cm: "99.999",
      length_cm: "",
    });
    const data = buildListingData(form);
    expect(data.price).toBe("10.50");
    expect(data.weight_kg).toBe("3.00");
    expect(data.height_cm).toBe("0.10");
    expect(data.width_cm).toBe("100.00");
    expect(data.length_cm).toBe("0.00");
  });
});
