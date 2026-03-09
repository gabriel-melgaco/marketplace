// src/routes/routePaths.ts

export const ROUTES = {
  // Públicas
  HOME: "/",
  PRODUCT_LIST: "/productlist",
  PRODUCT_DETAIL: "/productdetail/:id",
  CATEGORY_PRODUCTS: "/products",

  // Auth
  GOOGLE_CALLBACK: "/google",
  MELHOR_ENVIO_CALLBACK: "/auth/melhor-envio/callback",
  STRIPE_ONBOARDING_COMPLETE: "/seller/onboarding/complete",
  LOGIN: "/login",
  REGISTER: "/register",
  FORGOT_PASSWORD: "/forgotpassword",
  RESET_PASSWORD: "/reset-password",

  // Dashboard
  DASHBOARD: "/dashboard",
  CREATE_LISTING: "/create-listing",
  EDIT_AD: "/ad/:id",
  MY_PURCHASES: "/mypurchase",
  MY_SALES: "/mysales",
  MY_REVIEWS: "/myreviews",

  // Checkout
  CHECKOUT: "/checkout",
  PAYMENT: "/payment",
  ORDER_CONFIRMED: "/orderconfirmed",

  // Account
  ACCOUNT: "/account",
} as const;

// Função helper para criar rotas dinâmicas
export const createRoute = {
  productDetail: (id: string) => `/productdetail/${id}`,
  editAd: (id: string) => `/ad/${id}`,
};
