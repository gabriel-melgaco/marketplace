import api from "@/api/axios";
import type { Review, ReviewStats } from "@/types/review";
import type { PaginatedResponse } from "@/types/product";

export const reviewService = {
  async getReceivedReviews(params?: { page?: number }) {
    const response = await api.get<PaginatedResponse<Review>>(
      "/reviews/received/",
      { params },
    );
    return response.data;
  },

  async getSellerStats() {
    const response = await api.get<ReviewStats>("/reviews/stats/");
    return response.data;
  },
};
