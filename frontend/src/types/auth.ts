export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password1: string;
  password2: string;
  full_name: string;
  cpf: string;
  birthday: string; // formato: YYYY-MM-DD
  picture?: string;
}

export interface PasswordChangeRequest {
  old_password: string;
  new_password1: string;
  new_password2: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  new_password1: string;
  new_password2: string;
  uid: string;
  token: string;
}

export interface ResendEmailRequest {
  email: string;
}

export interface VerifyEmailRequest {
  key: string;
}

export interface LogoutRequest {
  refresh: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  birthday: string;
  cpf: string;
  /** Empty string ("") means no picture — use truthiness check before rendering. */
  picture: string;
  is_active: boolean;
  is_seller?: boolean;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  access_expiration: string;
  refresh_expiration: string;
  user: User;
}

export interface RegisterResponse {
  detail: string;
  full_name: string;
  cpf: string;
  birthday: string;
  picture: string;
}

export interface ApiResponse {
  detail: string;
}

export interface AuthContextData {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
  setUser: (user: User) => void;
}
