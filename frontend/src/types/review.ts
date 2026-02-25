export interface ReviewerInfo {
  id: number;
  full_name: string;
  picture: string | null;
}

export interface ReviewListingInfo {
  id: number;
  title: string;
}

export interface Review {
  id: number;
  reviewer: ReviewerInfo;
  listing: ReviewListingInfo;
  rating: number;
  comment: string;
  created_at: string;
}

export interface ReviewStats {
  average_rating: number;
  total_reviews: number;
  rating_breakdown: {
    1: number;
    2: number;
    3: number;
    4: number;
    5: number;
  };
}
