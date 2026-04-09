import api from "@/api/axios";
import type { AddListingImageRequest, MarketplaceListingImage } from "@/types/product";

export const listingImageService = {
  async addImage(listingId: number, data: AddListingImageRequest) {
    const response = await api.post<MarketplaceListingImage>(
      `/products/listings/${listingId}/images/`,
      data,
    );
    return response.data;
  },

  async setPrimary(listingId: number, imageId: number) {
    const response = await api.post(
      `/products/listings/${listingId}/images/${imageId}/set-primary/`,
    );
    return response.data;
  },

  async deleteImage(listingId: number, imageId: number) {
    await api.delete(
      `/products/listings/${listingId}/images/${imageId}/delete/`,
    );
  },
};
