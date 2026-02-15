# Frontend Services Documentation

This directory contains all API service modules for the marketplace frontend application.

## Service Files Overview

### Authentication & User Management

#### `authService.ts`
Handles user authentication and password management.
- `login(credentials)` - POST /auth/login/
- `logout()` - POST /auth/logout/
- `register(credentials)` - POST /auth/registration/
- `resendVerificationEmail(data)` - POST /auth/registration/resend-email/
- `verifyEmail(data)` - POST /auth/registration/verify-email/
- `changePassword(data)` - POST /auth/password/change/
- `requestPasswordReset(data)` - POST /auth/password/reset/
- `confirmPasswordReset(data)` - POST /auth/password/reset/confirm/
- `isAuthenticated()` - Check if user is authenticated
- `getCurrentUser()` - Get current user from storage
- `needsTokenRefresh()` - Check if token refresh is needed

#### `userService.ts`
Manages user profile operations.
- `getCurrentUser()` - GET /auth/user/
- `updateCurrentUser(data)` - PATCH /auth/user/
- `replaceCurrentUser(data)` - PUT /auth/user/

#### `socialAuthService.ts`
Handles social authentication (Google OAuth).
- `listSocialAccounts()` - GET /auth/social/accounts/
- `disconnectSocialAccount(id)` - DELETE /auth/social/accounts/{id}/
- `googleLogin(data)` - POST /auth/social/google/
- `googleConnect(data)` - POST /auth/social/google/connect/

### Products & Catalog

#### `productService.ts`
Manages marketplace listings and products.
- `getAll()` - GET /products/
- `getListings()` - GET /products/listings/
- `getById(id)` - GET /products/{id}/
- `getListingById(id)` - GET /products/listings/{id}/
- `incrementListingView(id)` - POST /products/listings/{id}/increment-view/
- `create(data)` - POST /products/
- `update(id, data)` - PUT /products/{id}/
- `delete(id)` - DELETE /products/{id}/
- `searchListings(term)` - GET /products/search/
- `createListing(data)` - POST /products/listings/create/
- `updateListing(id, data)` - PUT /products/listings/{id}/update/
- `getFilterOptions()` - GET /products/search/filters/options/
- `getProducts()` - GET /products/products/

#### `catalogService.ts`
Manages product catalog (brands, categories, series, conditions).
- `listBrands()` - GET /products/brands/
- `getBrand(slug)` - GET /products/brands/{slug}/
- `getBrandListings(slug)` - GET /products/brands/{slug}/listings/
- `listCategories()` - GET /products/categories/
- `getCategory(slug)` - GET /products/categories/{slug}/
- `getCategoryProducts(slug)` - GET /products/categories/{slug}/products/
- `listSeries()` - GET /products/series/
- `getSeries(slug)` - GET /products/series/{slug}/
- `getSeriesProducts(slug)` - GET /products/series/{slug}/products/
- `listConditions()` - GET /products/conditions/

#### `listingImageService.ts`
Manages marketplace listing images.
- `addImage(listingId, data)` - POST /products/listings/{listingId}/images/
- `setPrimary(listingId, imageId)` - POST /products/listings/{listingId}/images/{imageId}/set-primary/
- `deleteImage(listingId, imageId)` - DELETE /products/listings/{listingId}/images/{imageId}/delete/

### Orders & Cart

#### `cartService.ts`
Manages shopping cart operations.
- `getCart()` - GET /orders/cart/
- `addItem(data)` - POST /orders/cart/add/
- `updateItem(itemId, data)` - PATCH /orders/cart/items/{itemId}/
- `removeItem(itemId)` - DELETE /orders/cart/items/{itemId}/remove/
- `clearCart()` - DELETE /orders/cart/clear/

#### `orderService.ts`
Manages orders for buyers and sellers.

Buyer endpoints:
- `listOrders()` - GET /orders/
- `getOrder(id)` - GET /orders/{id}/
- `createOrder(data)` - POST /orders/create/
- `cancelOrder(id)` - POST /orders/{id}/cancel/

Seller endpoints:
- `listSales()` - GET /orders/sales/
- `getSale(id)` - GET /orders/sales/{id}/
- `updateOrderStatus(id, data)` - POST /orders/sales/{id}/update-status/

### Payments

#### `paymentService.ts`
Handles payment processing and seller payouts.
- `listPayments()` - GET /payments/
- `getPayment(id)` - GET /payments/{id}/
- `createPaymentIntent(data)` - POST /payments/create-intent/
- `getPaymentStatus(paymentIntentId)` - GET /payments/status/{paymentIntentId}/
- `confirmPayment(data)` - POST /payments/confirm/
- `requestRefund(data)` - POST /payments/refund/
- `getBalance()` - GET /payments/balance/
- `listPayouts()` - GET /payments/payouts/
- `getPayout(id)` - GET /payments/payouts/{id}/

#### `stripeConnectService.ts`
Manages Stripe Connect accounts for sellers.
- `createConnectedAccount()` - POST /payments/connect/create/
- `getOnboardingLink()` - POST /payments/connect/onboarding-link/
- `getAccountStatus()` - GET /payments/connect/status/
- `createCheckoutWithConnect(data)` - POST /payments/connect/checkout/

### Logistics

#### `addressService.ts`
Manages user addresses and CEP lookup.
- `listAddresses()` - GET /logistics/addresses/
- `getAddress(id)` - GET /logistics/addresses/{id}/
- `createAddress(data)` - POST /logistics/addresses/
- `updateAddress(id, data)` - PATCH /logistics/addresses/{id}/
- `deleteAddress(id)` - DELETE /logistics/addresses/{id}/
- `setDefaultAddress(id)` - POST /logistics/addresses/{id}/set-default/
- `getShippingAddresses()` - GET /logistics/addresses/shipping/
- `lookupCEP(data)` - POST /logistics/cep/lookup/

#### `shippingService.ts`
Manages shipping calculations and shipments.
- `calculateShipping(data)` - POST /logistics/shipping/calculate/
- `getSavedQuotes()` - GET /logistics/shipping/quotes/
- `listShipments()` - GET /logistics/shipments/
- `getShipment(id)` - GET /logistics/shipments/{id}/
- `createShipments(data)` - POST /logistics/shipments/create/
- `getOrderShipments(orderId)` - GET /logistics/shipments/order/{orderId}/
- `generateLabel(shipmentId)` - POST /logistics/shipments/{shipmentId}/label/
- `trackShipment(shipmentId)` - POST /logistics/shipments/{shipmentId}/track/

#### `deliveryService.ts`
Manages order deliveries (combined shipping + in-person).
- `createOrderDeliveries(data)` - POST /logistics/deliveries/create/
- `getOrderDeliveries(orderId)` - GET /logistics/deliveries/order/{orderId}/
- `getUserDeliveries()` - GET /logistics/deliveries/user/

#### `inPersonDeliveryService.ts`
Manages in-person pickup deliveries.
- `listInPersonDeliveries(params)` - GET /logistics/in-person/
- `getInPersonDelivery(id)` - GET /logistics/in-person/{id}/
- `updateMeeting(id, data)` - PATCH /logistics/in-person/{id}/update/
- `confirmMeeting(id)` - POST /logistics/in-person/{id}/confirm/
- `completeDelivery(id, data)` - POST /logistics/in-person/{id}/complete/
- `cancelDelivery(id, data)` - POST /logistics/in-person/{id}/cancel/

### Storage

#### `storageService.ts`
Manages file uploads to S3.
- `getPresignedUrl(fileName, contentType)` - POST /storage/upload/presigned-url/
- `uploadToS3(uploadUrl, file)` - Direct S3 upload

## Usage

Import services from the barrel file:

```typescript
import { 
  authService, 
  productService, 
  cartService, 
  orderService 
} from '@/services';

// Use the service
const products = await productService.getListings();
```

Or import individually:

```typescript
import { cartService } from '@/services/cartService';

const cart = await cartService.getCart();
```

## Type Safety

All services include TypeScript interfaces for request/response types. Import types as needed:

```typescript
import type { 
  AddToCartRequest, 
  Cart 
} from '@/services/cartService';

const addToCart = async (data: AddToCartRequest): Promise<Cart> => {
  return await cartService.addItem(data);
};
```

## API Base URL

All services use the configured axios instance from `@/api/axios.ts` which:
- Sets the base URL from environment variables
- Automatically includes JWT authentication headers
- Handles token refresh interceptors
