import { createBrowserRouter } from "react-router-dom";
import HomeLayout from "@/layout/homelayout";
import Home from "@/pages/public/Home";
import { ProductDetail } from "@/pages/public/ProductDetail";
import { ProductList } from "@/pages/public/ProductList";
import LoginPage from "@/pages/auth/Login";
import { ForgotPassword } from "@/pages/auth/ForgotPassword";
import ResetPassword from "@/pages/auth/ResetPassword";
import { Register } from "@/pages/auth/Register";
import { Checkout } from "@/pages/Checkout/ClientcheCkout";
import { Payment } from "@/pages/Checkout/ClientPayment";
import { OrderConfirmed } from "@/pages/Checkout/OrderConfirmed";
import { Dashboard } from "@/pages/Dashboard/ClientDashboard";
import { ListingForm } from "@/pages/Dashboard/ListingForm";
import { MyPurchase } from "@/pages/Dashboard/MyPurchases";
import { MySales } from "@/pages/Dashboard/MySales";
import { MyReviews } from "@/pages/Dashboard/MyReviews";
import PivateRoutes from "@/routes/PrivateRoutes";
import EmailSent from "@/pages/auth/EmailSent";
import ConfirmEmail from "@/pages/auth/ConfirmEmail";
import { Chat } from "@/pages/private/Chat";
import { StateProductList } from "@/pages/public/StateProductList";

const router = createBrowserRouter([
  // 🌍 PÚBLICAS COM LAYOUT
  {
    path: "/",
    element: <HomeLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: "productlist", element: <ProductList /> },
      { path: "productdetail/:id", element: <ProductDetail /> },
      { path: "estado/:uf", element: <StateProductList /> },
    ],
  },

  // 🔐 AUTH (SEM HEADER)
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <Register /> },
  { path: "/forgotpassword", element: <ForgotPassword /> },
  { path: "/reset-password", element: <ResetPassword /> },
  { path: "/email-sent", element: <EmailSent /> },
  { path: "/confirm-email", element: <ConfirmEmail /> },

  // 🔒 PRIVADAS
  {
    element: <PivateRoutes />,
    children: [
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
          { path: "orderconfirmed", element: <OrderConfirmed /> },
          { path: "chat/:listingId?", element: <Chat /> },
        ],
      },
    ],
  },
]);

export { router };
