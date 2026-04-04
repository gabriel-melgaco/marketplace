import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./App";
import "./index.css";
import { AuthProvider } from "./contexts/AuthContext";
import { CartProvider } from "./contexts/CartContext";
import { NotificationProvider } from "./contexts/NotificationContext";
import { ChatProvider } from "./contexts/ChatContext";
import { CookieBanner } from "./components/ui/CookieBanner";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <NotificationProvider>
        <ChatProvider>
        <CartProvider>
          <RouterProvider router={router} />
          <CookieBanner />
        </CartProvider>
        </ChatProvider>
      </NotificationProvider>
    </AuthProvider>
  </React.StrictMode>,
);
