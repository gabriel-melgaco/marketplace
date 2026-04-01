import { createBrowserRouter } from "react-router-dom";
import HomeLayout from "@/layout/homelayout";
import Home from "@/pages/public/Home";
import { ProductDetail } from "@/pages/public/ProductDetail";
import { ProductList } from "@/pages/public/ProductList";
import LoginPage from "@/pages/auth/Login";
import { ForgotPassword } from "@/pages/auth/ForgotPassword";
import ResetPassword from "@/pages/auth/ResetPassword";
import { Register } from "@/pages/auth/Register";
import { Checkout } from "@/pages/Checkout/ClientCheckout";
import { Payment } from "@/pages/Payment";
import { PaymentSuccess } from "@/pages/Payment/PaymentSuccess";
import { PaymentProcessing } from "@/pages/Payment/PaymentProcessing";
import { PaymentFailed } from "@/pages/Payment/PaymentFailed";
import { OrderConfirmed } from "@/pages/Checkout/OrderConfirmed";
import { Dashboard } from "@/pages/Dashboard/ClientDashboard";
import { ListingForm } from "@/pages/Dashboard/ListingForm";
import { MyPurchase } from "@/pages/Dashboard/MyPurchases";
import { MySales } from "@/pages/Dashboard/MySales";
import { MyReviews } from "@/pages/Dashboard/MyReviews";
import PrivateRoutes from "@/routes/PrivateRoutes";
import EmailSent from "@/pages/auth/EmailSent";
import ConfirmEmail from "@/pages/auth/ConfirmEmail";
import { Chat } from "@/pages/private/Chat";
import { AccountPage } from "@/pages/account";
import { StateProductList } from "@/pages/public/StateProductList";
import { GoogleCallback } from "@/pages/auth/GoogleCallback";
import { MelhorEnvioCallback } from "@/pages/auth/MelhorEnvioCallback";
import { StripeOnboardingComplete } from "@/pages/seller/onboarding/complete";
import { CategoryProductList } from "@/pages/public/CategoryProductList";
import { NotFound } from "@/pages/public/NotFound";
import { ROUTES } from "@/routes/routePaths";
import { ConversationsPage } from "@/pages/Conversations";
import { ConversationDetail } from "@/pages/Conversations/ConversationDetail";
import ChatLayout from "@/layout/chatlayout";

const router = createBrowserRouter([
  // PUBLIC — with shared layout
  {
    path: "/",
    element: <HomeLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: "productlist", element: <ProductList /> },
      { path: "productdetail/:id", element: <ProductDetail /> },
      { path: "estado/:uf", element: <StateProductList /> },
      { path: "products", element: <CategoryProductList /> },
    ],
  },

  // AUTH — no shared header
  { path: ROUTES.GOOGLE_CALLBACK, element: <GoogleCallback /> },
  { path: ROUTES.MELHOR_ENVIO_CALLBACK, element: <MelhorEnvioCallback /> },
  { path: ROUTES.STRIPE_ONBOARDING_COMPLETE, element: <StripeOnboardingComplete /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <Register /> },
  { path: "/forgotpassword", element: <ForgotPassword /> },
  { path: "/reset-password", element: <ResetPassword /> },
  { path: "/email-sent", element: <EmailSent /> },
  { path: "/confirm-email", element: <ConfirmEmail /> },

  // PRIVATE — require authentication
  {
    element: <PrivateRoutes />,
    children: [
      // Pages that use the standard scrollable layout
      {
        element: <HomeLayout />,
        children: [
          { path: "dashboard", element: <Dashboard /> },
          { path: "create-listing", element: <ListingForm /> },
          { path: "ad/:id", element: <ListingForm /> },
          { path: "mypurchase", element: <MyPurchase /> },
          { path: "mysales", element: <MySales /> },
          { path: "myreviews", element: <MyReviews /> },
          { path: "checkout", element: <Checkout /> },
          { path: "payment", element: <Payment /> },
          { path: "payment/success", element: <PaymentSuccess /> },
          { path: "payment/processing", element: <PaymentProcessing /> },
          { path: "payment/failed", element: <PaymentFailed /> },
          { path: "orderconfirmed", element: <OrderConfirmed /> },
          { path: "chat/:listingId?", element: <Chat /> },
          { path: "account", element: <AccountPage /> },
        ],
      },
      // Chat routes — use ChatLayout so the message area scrolls internally
      {
        element: <ChatLayout />,
        children: [
          { path: "conversations", element: <ConversationsPage /> },
          { path: "conversations/:id", element: <ConversationDetail /> },
        ],
      },
    ],
  },

  // CATCH-ALL — no layout (standalone NotFound page)
  { path: "*", element: <NotFound /> },
]);

export { router };
