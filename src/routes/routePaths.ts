// src/routes/routePaths.ts

export const ROUTES = {
  // Públicas
  HOME: "/",
  PRODUCT_LIST: "/productlist",
  PRODUCT_DETAIL: "/productdetail/:id",

  // Auth
  LOGIN: "/login",
  REGISTER: "/register",
  FORGOT_PASSWORD: "/forgotpassword",
  RESET_PASSWORD: "/resetpassword",

  // Dashboard
  DASHBOARD: "/dashboard",
  EDIT_AD: "/ad/:id",
  MY_PURCHASES: "/mypurchase",
  MY_SALES: "/mysales",
  MY_REVIEWS: "/myreviews",

  // Checkout
  CHECKOUT: "/checkout",
  PAYMENT: "/payment",
  ORDER_CONFIRMED: "/orderconfirmed",
} as const;

// Função helper para criar rotas dinâmicas
export const createRoute = {
  productDetail: (id: string) => `/productdetail/${id}`,
  editAd: (id: string) => `/ad/${id}`,
};
