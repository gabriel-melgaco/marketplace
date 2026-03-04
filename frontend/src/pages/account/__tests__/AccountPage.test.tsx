/**
 * Tests for src/pages/account/index.tsx
 *
 * Framework: Vitest + @testing-library/react + jsdom
 *
 * Strategy:
 *  - Mock all service modules and the AuthContext.
 *  - Control Swal.fire outcomes to simulate user confirmation/cancellation.
 *  - Test critical flows: save personal data, change password, address CRUD,
 *    Google account linking, and account deletion.
 *
 * Risk level: HIGH
 *  - Save personal data writes to tokenStorage and AuthContext — a regression
 *    causes the profile-completion modal to re-appear on every login.
 *  - Delete account bypasses confirmation — permanent data loss.
 *  - Password change must block weak / mismatched passwords client-side.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/utils/constants", () => ({
  API_BASE_URL: "http://localhost:8000/api",
  MINIO_PUBLIC_URL: "http://localhost:9000",
  GOOGLE_CLIENT_ID: "test",
  GOOGLE_REDIRECT_URI: "http://localhost:5173/google",
  PAGINATION: { DEFAULT_PAGE_SIZE: 20, MAX_PAGE_SIZE: 100 },
}));

const mockSetUser = vi.fn();
const mockLogout = vi.fn();

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
      birthday: "1990-05-15",
      cpf: "12345678909",
      picture: "",
      is_active: true,
    },
    setUser: mockSetUser,
    logout: mockLogout,
  }),
}));

const mockUpdateCurrentUser = vi.fn();
vi.mock("@/services/userService", () => ({
  userService: { updateCurrentUser: (...args: any[]) => mockUpdateCurrentUser(...args) },
}));

const mockChangePassword = vi.fn();
vi.mock("@/services/authService", () => ({
  authService: { changePassword: (...args: any[]) => mockChangePassword(...args) },
}));

const mockListSocialAccounts = vi.fn();
vi.mock("@/services/socialAuthService", () => ({
  socialAuthService: { listSocialAccounts: () => mockListSocialAccounts() },
}));

const mockGetAddresses = vi.fn();
const mockCreateAddress = vi.fn();
const mockDeleteAddress = vi.fn();
const mockLookupCep = vi.fn();
vi.mock("@/services/logisticsService", () => ({
  logisticsService: {
    getAddresses: () => mockGetAddresses(),
    createAddress: (...args: any[]) => mockCreateAddress(...args),
    deleteAddress: (...args: any[]) => mockDeleteAddress(...args),
    lookupCep: (...args: any[]) => mockLookupCep(...args),
  },
}));

const mockSaveUser = vi.fn();
vi.mock("@/utils/tokenStorage", () => ({
  tokenStorage: { saveUser: (...args: any[]) => mockSaveUser(...args) },
}));

const mockStartGoogleOAuth = vi.fn();
vi.mock("@/hooks/useGoogleAuth", () => ({
  startGoogleOAuth: (...args: any[]) => mockStartGoogleOAuth(...args),
}));

const mockApiDelete = vi.fn();
vi.mock("@/api/axios", () => ({
  default: { delete: (...args: any[]) => mockApiDelete(...args) },
}));

import Swal from "sweetalert2";
vi.mock("sweetalert2", () => ({ default: { fire: vi.fn() } }));
const mockSwalFire = Swal.fire as ReturnType<typeof vi.fn>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

import { AccountPage } from "../index";

function renderAccountPage() {
  return render(
    <MemoryRouter>
      <AccountPage />
    </MemoryRouter>,
  );
}

async function navigateToSection(label: string) {
  // Works for both mobile and desktop nav buttons
  const buttons = screen.getAllByRole("button", { name: label });
  await userEvent.click(buttons[0]);
}

// ─── Helper functions — tested via rendering ──────────────────────────────────

describe("AccountPage - helper functions via rendered output", () => {
  it("renders CPF in formatted display (xxx.xxx.xxx-xx)", () => {
    renderAccountPage();
    const cpfInput = screen.getByDisplayValue("123.456.789-09");
    expect(cpfInput).toBeInTheDocument();
  });

  it("renders birthday in DD/MM/YYYY format when stored as ISO", () => {
    renderAccountPage();
    const birthdayInput = screen.getByDisplayValue("15/05/1990");
    expect(birthdayInput).toBeInTheDocument();
  });
});

// ─── Navigation ───────────────────────────────────────────────────────────────

describe("AccountPage - Navigation", () => {
  it("renders 'Dados Pessoais' section by default", () => {
    renderAccountPage();
    expect(screen.getAllByText("Dados Pessoais").length).toBeGreaterThan(0);
  });

  it("renders sidebar navigation with four section items", () => {
    renderAccountPage();
    expect(screen.getAllByRole("button", { name: /Dados Pessoais/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Endereços/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Segurança/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Notificações/i }).length).toBeGreaterThan(0);
  });

  it("active nav button has aria-current='page'", () => {
    renderAccountPage();
    const activeButtons = screen.getAllByRole("button", { name: /Dados Pessoais/i });
    expect(activeButtons[0]).toHaveAttribute("aria-current", "page");
  });

  it("switches to Addresses section on click", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => {
      expect(screen.getByText("Meus Endereços")).toBeInTheDocument();
    });
  });
});

// ─── Dados Pessoais ───────────────────────────────────────────────────────────

describe("AccountPage - Dados Pessoais", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders full name input pre-filled with user name from context", () => {
    renderAccountPage();
    expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
  });

  it("renders email as read-only", () => {
    renderAccountPage();
    const emailInput = screen.getByDisplayValue("test@example.com");
    expect(emailInput).toHaveAttribute("readonly");
  });

  it("shows error when form is submitted with empty full name", async () => {
    renderAccountPage();
    const nameInput = screen.getByDisplayValue("Test User");
    await userEvent.clear(nameInput);
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(screen.getByText("Nome completo é obrigatório.")).toBeInTheDocument();
    expect(mockUpdateCurrentUser).not.toHaveBeenCalled();
  });

  it("shows error when full name is only whitespace", async () => {
    renderAccountPage();
    const nameInput = screen.getByDisplayValue("Test User");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "   ");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(screen.getByText("Nome completo é obrigatório.")).toBeInTheDocument();
    expect(mockUpdateCurrentUser).not.toHaveBeenCalled();
  });

  it("calls updateCurrentUser with trimmed name on valid submit", async () => {
    mockUpdateCurrentUser.mockResolvedValue({
      id: 1,
      email: "test@example.com",
      full_name: "João Silva",
      birthday: "1990-05-15",
      cpf: "12345678909",
      picture: "",
    });
    renderAccountPage();
    const nameInput = screen.getByDisplayValue("Test User");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, " João Silva ");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(mockUpdateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ full_name: "João Silva" }),
      );
    });
  });

  it("does NOT include birthday in payload when birthday is shorter than 10 chars", async () => {
    mockUpdateCurrentUser.mockResolvedValue({
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
      birthday: "1990-05-15",
      cpf: "12345678909",
      picture: "",
    });
    renderAccountPage();
    const birthdayInput = screen.getByDisplayValue("15/05/1990");
    await userEvent.clear(birthdayInput);
    await userEvent.type(birthdayInput, "12/05");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      const call = mockUpdateCurrentUser.mock.calls[0][0];
      expect(call).not.toHaveProperty("birthday");
    });
  });

  it("includes birthday in ISO format when birthday is 10 chars", async () => {
    mockUpdateCurrentUser.mockResolvedValue({
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
      birthday: "2000-01-20",
      cpf: "12345678909",
      picture: "",
    });
    renderAccountPage();
    const birthdayInput = screen.getByDisplayValue("15/05/1990");
    await userEvent.clear(birthdayInput);
    await userEvent.type(birthdayInput, "20/01/2000");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(mockUpdateCurrentUser).toHaveBeenCalledWith(
        expect.objectContaining({ birthday: "2000-01-20" }),
      );
    });
  });

  it("calls tokenStorage.saveUser and setUser after successful save", async () => {
    const updatedUser = {
      id: 1,
      email: "test@example.com",
      full_name: "Updated Name",
      birthday: "1990-05-15",
      cpf: "12345678909",
      picture: "",
    };
    mockUpdateCurrentUser.mockResolvedValue(updatedUser);
    renderAccountPage();
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(mockSaveUser).toHaveBeenCalled();
      expect(mockSetUser).toHaveBeenCalled();
    });
  });

  it("shows success message after successful save", async () => {
    mockUpdateCurrentUser.mockResolvedValue({
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
      birthday: "1990-05-15",
      cpf: "12345678909",
      picture: "",
    });
    renderAccountPage();
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(screen.getByText("Dados salvos com sucesso!")).toBeInTheDocument();
    });
  });

  it("shows error message from API field-level response", async () => {
    mockUpdateCurrentUser.mockRejectedValue({
      response: { data: { full_name: ["Este campo não pode ser em branco."] } },
    });
    renderAccountPage();
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(screen.getByText("Este campo não pode ser em branco.")).toBeInTheDocument();
    });
  });
});

// ─── Endereços ────────────────────────────────────────────────────────────────

describe("AccountPage - Endereços", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls getAddresses when Endereços section is activated", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => expect(mockGetAddresses).toHaveBeenCalledTimes(1));
  });

  it("does NOT call getAddresses on initial render", () => {
    renderAccountPage();
    expect(mockGetAddresses).not.toHaveBeenCalled();
  });

  it("shows empty state when address list is empty", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => {
      expect(screen.getByText("Nenhum endereço cadastrado.")).toBeInTheDocument();
    });
  });

  it("renders a card for each address returned by the API", async () => {
    mockGetAddresses.mockResolvedValue([
      { id: 1, nickname: "Casa", street: "Rua A", number: "10", city: "SP", state: "SP", zipcode: "01001000", is_default: false, complement: "", neighborhood: "Bairro", country: "BR", address_type: "Residencial", is_active: true },
      { id: 2, nickname: "Trabalho", street: "Rua B", number: "20", city: "SP", state: "SP", zipcode: "01002000", is_default: true, complement: "", neighborhood: "Centro", country: "BR", address_type: "Comercial", is_active: true },
    ]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => {
      expect(screen.getByText("Casa")).toBeInTheDocument();
      expect(screen.getByText("Trabalho")).toBeInTheDocument();
    });
  });

  it("shows Padrão badge on is_default address", async () => {
    mockGetAddresses.mockResolvedValue([
      { id: 1, nickname: "Casa", street: "Rua A", number: "10", city: "SP", state: "SP", zipcode: "01001000", is_default: true, complement: "", neighborhood: "Bairro", country: "BR", address_type: "Residencial", is_active: true },
    ]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => {
      expect(screen.getByText("Padrão")).toBeInTheDocument();
    });
  });

  it("opens AddressModal when 'Novo endereço' is clicked", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => screen.getByText("Nenhum endereço cadastrado."));
    await userEvent.click(screen.getByRole("button", { name: /Novo endereço/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Novo Endereço")).toBeInTheDocument();
  });

  it("closes AddressModal without saving when Cancelar is clicked", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => screen.getByText("Nenhum endereço cadastrado."));
    await userEvent.click(screen.getByRole("button", { name: /Novo endereço/i }));
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockCreateAddress).not.toHaveBeenCalled();
  });

  it("shows validation errors on empty form submit", async () => {
    mockGetAddresses.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => screen.getByText("Nenhum endereço cadastrado."));
    await userEvent.click(screen.getByRole("button", { name: /Novo endereço/i }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar endereço" }));
    await waitFor(() => {
      expect(screen.getAllByText("Campo obrigatório").length).toBeGreaterThan(0);
    });
    expect(mockCreateAddress).not.toHaveBeenCalled();
  });

  it("address is NOT deleted when user cancels confirmation", async () => {
    mockGetAddresses.mockResolvedValue([
      { id: 1, nickname: "Casa", street: "Rua A", number: "10", city: "SP", state: "SP", zipcode: "01001000", is_default: false, complement: "", neighborhood: "Bairro", country: "BR", address_type: "Residencial", is_active: true },
    ]);
    mockSwalFire.mockResolvedValue({ isConfirmed: false });
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => screen.getByText("Casa"));
    await userEvent.click(screen.getByTitle("Remover endereço"));
    expect(mockDeleteAddress).not.toHaveBeenCalled();
    expect(screen.getByText("Casa")).toBeInTheDocument();
  });

  it("removes address from list when user confirms deletion", async () => {
    mockGetAddresses.mockResolvedValue([
      { id: 1, nickname: "Casa", street: "Rua A", number: "10", city: "SP", state: "SP", zipcode: "01001000", is_default: false, complement: "", neighborhood: "Bairro", country: "BR", address_type: "Residencial", is_active: true },
    ]);
    mockSwalFire.mockResolvedValue({ isConfirmed: true });
    mockDeleteAddress.mockResolvedValue(undefined);
    renderAccountPage();
    await navigateToSection("Endereços");
    await waitFor(() => screen.getByText("Casa"));
    await userEvent.click(screen.getByTitle("Remover endereço"));
    await waitFor(() => {
      expect(screen.queryByText("Casa")).not.toBeInTheDocument();
      expect(screen.getByText("Nenhum endereço cadastrado.")).toBeInTheDocument();
    });
  });
});

// ─── Segurança — Alterar Senha ────────────────────────────────────────────────

describe("AccountPage - Segurança - Alterar Senha", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockListSocialAccounts.mockResolvedValue([]);
  });

  async function goToSecurity() {
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => screen.getByText("Alterar Senha"));
  }

  it("shows error when all password fields are empty on submit", async () => {
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    expect(screen.getByText("Preencha todos os campos.")).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("shows 'As senhas não coincidem.' when new passwords differ", async () => {
    await goToSecurity();
    const passwordInputs = document.querySelectorAll<HTMLInputElement>("input[type='password']");
    await userEvent.type(passwordInputs[0], "currentPass1");
    await userEvent.type(passwordInputs[1], "newPass1234");
    await userEvent.type(passwordInputs[2], "different456");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    expect(screen.getByText("As senhas não coincidem.")).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("shows length error when new password is shorter than 8 chars", async () => {
    await goToSecurity();
    const passwordInputs = document.querySelectorAll<HTMLInputElement>("input[type='password']");
    await userEvent.type(passwordInputs[0], "currentPass1");
    await userEvent.type(passwordInputs[1], "short1");
    await userEvent.type(passwordInputs[2], "short1");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    expect(screen.getByText("A nova senha deve ter pelo menos 8 caracteres.")).toBeInTheDocument();
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("calls changePassword and clears fields on success", async () => {
    mockChangePassword.mockResolvedValue({ detail: "New password has been saved." });
    await goToSecurity();
    const passwordInputs = document.querySelectorAll<HTMLInputElement>("input[type='password']");
    await userEvent.type(passwordInputs[0], "currentPass1");
    await userEvent.type(passwordInputs[1], "newPass1234");
    await userEvent.type(passwordInputs[2], "newPass1234");
    await userEvent.click(screen.getByRole("button", { name: "Alterar senha" }));
    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith(
        expect.objectContaining({
          old_password: "currentPass1",
          new_password1: "newPass1234",
          new_password2: "newPass1234",
        }),
      );
      expect(screen.getByText("Senha alterada com sucesso!")).toBeInTheDocument();
    });
  });

  it("toggles password visibility when eye icon is clicked", async () => {
    await goToSecurity();
    const passwordInputs = document.querySelectorAll<HTMLInputElement>("input[type='password']");
    expect(passwordInputs[0].type).toBe("password");
    const toggleButtons = screen.getAllByRole("button", { name: /Mostrar senha/i });
    await userEvent.click(toggleButtons[0]);
    await waitFor(() => {
      const updated = document.querySelectorAll<HTMLInputElement>("input[type='text']");
      expect(updated.length).toBeGreaterThan(0);
    });
  });
});

// ─── Segurança — Conta Google ─────────────────────────────────────────────────

describe("AccountPage - Segurança - Conta Google", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls listSocialAccounts when security section is activated", async () => {
    mockListSocialAccounts.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => expect(mockListSocialAccounts).toHaveBeenCalledTimes(1));
  });

  it("shows 'Google conectado' when a Google social account exists", async () => {
    mockListSocialAccounts.mockResolvedValue([
      { id: 1, provider: "google", uid: "123", extra_data: { email: "g@gmail.com" }, date_joined: "" },
    ]);
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => {
      expect(screen.getByText("Google conectado")).toBeInTheDocument();
      expect(screen.getByText("g@gmail.com")).toBeInTheDocument();
      expect(screen.getByText("Conectado")).toBeInTheDocument();
    });
  });

  it("shows 'Vincular conta Google' button when no Google account is linked", async () => {
    mockListSocialAccounts.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Vincular conta Google/i })).toBeInTheDocument();
    });
  });

  it("calls startGoogleOAuth('connect') when vincular button is clicked", async () => {
    mockListSocialAccounts.mockResolvedValue([]);
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => screen.getByRole("button", { name: /Vincular conta Google/i }));
    await userEvent.click(screen.getByRole("button", { name: /Vincular conta Google/i }));
    expect(mockStartGoogleOAuth).toHaveBeenCalledWith("connect");
  });
});

// ─── Zona de Perigo ───────────────────────────────────────────────────────────

describe("AccountPage - Zona de Perigo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListSocialAccounts.mockResolvedValue([]);
  });

  async function goToSecurity() {
    renderAccountPage();
    await navigateToSection("Segurança");
    await waitFor(() => screen.getByText("Zona de perigo"));
  }

  it("renders the danger zone section", async () => {
    await goToSecurity();
    expect(screen.getByText("Zona de perigo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Excluir minha conta" })).toBeInTheDocument();
  });

  it("opens SweetAlert2 dialog when delete button is clicked", async () => {
    mockSwalFire.mockResolvedValue({ isConfirmed: false });
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    expect(mockSwalFire).toHaveBeenCalledWith(
      expect.objectContaining({ input: "text", inputPlaceholder: "EXCLUIR" }),
    );
  });

  it("does NOT delete when user cancels", async () => {
    mockSwalFire.mockResolvedValue({ isConfirmed: false });
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    await waitFor(() => {
      expect(mockApiDelete).not.toHaveBeenCalled();
      expect(mockLogout).not.toHaveBeenCalled();
    });
  });

  it("calls api.delete and logout on confirmed deletion", async () => {
    mockSwalFire.mockResolvedValue({ isConfirmed: true, value: "EXCLUIR" });
    mockApiDelete.mockResolvedValue(undefined);
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalledWith("/auth/user/");
      expect(mockLogout).toHaveBeenCalled();
    });
  });

  it("shows 'Funcionalidade em implementação' on 404 response", async () => {
    mockSwalFire
      .mockResolvedValueOnce({ isConfirmed: true, value: "EXCLUIR" })
      .mockResolvedValueOnce(undefined);
    mockApiDelete.mockRejectedValue({ response: { status: 404 } });
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    await waitFor(() => {
      expect(mockSwalFire).toHaveBeenCalledTimes(2);
      expect(mockSwalFire).toHaveBeenLastCalledWith(
        "Funcionalidade em implementação",
        expect.any(String),
        "info",
      );
    });
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("shows 'Funcionalidade em implementação' on 405 response", async () => {
    mockSwalFire
      .mockResolvedValueOnce({ isConfirmed: true, value: "EXCLUIR" })
      .mockResolvedValueOnce(undefined);
    mockApiDelete.mockRejectedValue({ response: { status: 405 } });
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    await waitFor(() => {
      expect(mockSwalFire).toHaveBeenLastCalledWith(
        "Funcionalidade em implementação",
        expect.any(String),
        "info",
      );
    });
  });

  it("shows generic error on 500 response", async () => {
    mockSwalFire
      .mockResolvedValueOnce({ isConfirmed: true, value: "EXCLUIR" })
      .mockResolvedValueOnce(undefined);
    mockApiDelete.mockRejectedValue({ response: { status: 500 } });
    await goToSecurity();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    await waitFor(() => {
      expect(mockSwalFire).toHaveBeenLastCalledWith(
        "Erro",
        expect.any(String),
        "error",
      );
    });
  });
});

// ─── Notificações ─────────────────────────────────────────────────────────────

describe("AccountPage - Notificações", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders four notification toggles", async () => {
    renderAccountPage();
    await navigateToSection("Notificações");
    await waitFor(() => {
      const switches = screen.getAllByRole("switch");
      expect(switches).toHaveLength(4);
    });
  });

  it("'Atualizações de pedidos' is ON by default", async () => {
    renderAccountPage();
    await navigateToSection("Notificações");
    await waitFor(() => {
      const toggle = screen.getByRole("switch", { name: "Atualizações de pedidos" });
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });
  });

  it("all other toggles are OFF by default", async () => {
    renderAccountPage();
    await navigateToSection("Notificações");
    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "Novos anúncios na sua busca" })).toHaveAttribute("aria-checked", "false");
      expect(screen.getByRole("switch", { name: "Mensagens recebidas" })).toHaveAttribute("aria-checked", "false");
      expect(screen.getByRole("switch", { name: "Promoções e novidades" })).toHaveAttribute("aria-checked", "false");
    });
  });

  it("renders 'Em breve' under each notification item", async () => {
    renderAccountPage();
    await navigateToSection("Notificações");
    await waitFor(() => {
      expect(screen.getAllByText("Em breve")).toHaveLength(4);
    });
  });
});
