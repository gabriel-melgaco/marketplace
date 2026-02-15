// Authentication & User
export { authService } from "./authService";
export { userService } from "./userService";
export { socialAuthService } from "./socialAuthService";

// Products & Catalog
export { productService } from "./productService";
export { catalogService } from "./catalogService";
export { listingImageService } from "./listingImageService";

// Orders & Cart
export { cartService } from "./cartService";
export { orderService } from "./orderService";

// Payments
export { paymentService } from "./paymentService";
export { stripeConnectService } from "./stripeConnectService";

// Logistics
export { addressService } from "./addressService";
export { shippingService } from "./shippingService";
export { deliveryService } from "./deliveryService";
export { inPersonDeliveryService } from "./inPersonDeliveryService";

// Storage
export { storageService } from "./storageService";

// Re-export types for convenience
export type * from "./authService";
export type * from "./productService";
export type * from "./cartService";
export type * from "./orderService";
export type * from "./paymentService";
export type * from "./stripeConnectService";
export type * from "./addressService";
export type * from "./shippingService";
export type * from "./deliveryService";
export type * from "./inPersonDeliveryService";
export type * from "./catalogService";
export type * from "./socialAuthService";
export type * from "./userService";
