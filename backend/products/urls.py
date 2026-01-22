from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # =================== Categories ===================
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', views.CategoryDetailView.as_view(), name='category-detail'),
    path('categories/<slug:slug>/products/', views.CategoryProductsView.as_view(), name='category-products'),
    
    # =================== Series ===================
    path('series/', views.SeriesListView.as_view(), name='series-list'),
    path('series/<slug:slug>/', views.SeriesDetailView.as_view(), name='series-detail'),
    path('series/<slug:slug>/products/', views.SeriesProductsView.as_view(), name='series-products'),
    
    # =================== Products ===================
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<slug:slug>/listings/', views.ProductListingsView.as_view(), name='product-listings'),
    
    # =================== Brands ===================
    path('brands/', views.BrandListView.as_view(), name='brand-list'),
    path('brands/<slug:slug>/', views.BrandDetailView.as_view(), name='brand-detail'),
    path('brands/<slug:slug>/listings/', views.BrandListingsView.as_view(), name='brand-listings'),
    
    # =================== Conditions ===================
    path('conditions/', views.ConditionListView.as_view(), name='condition-list'),
    
    # =================== Marketplace Listings (Public) ===================
    path('listings/', views.MarketplaceListingListView.as_view(), name='listing-list'),
    path('listings/<int:pk>/', views.MarketplaceListingDetailView.as_view(), name='listing-detail'),
    path('listings/<int:pk>/increment-view/', views.increment_view_count, name='listing-increment-view'),
    
    # =================== Marketplace Listings (Authenticated) ===================
    path('listings/create/', views.MarketplaceListingCreateView.as_view(), name='listing-create'),
    path('my-listings/', views.MyListingsView.as_view(), name='my-listings'),
    path('listings/<int:pk>/update/', views.MarketplaceListingUpdateView.as_view(), name='listing-update'),
    path('listings/<int:pk>/delete/', views.MarketplaceListingDeleteView.as_view(), name='listing-delete'),
    path('listings/<int:pk>/activate/', views.toggle_listing_active, name='listing-activate'),
    path('listings/<int:pk>/mark-as-sold/', views.mark_as_sold, name='listing-mark-sold'),
    
    # =================== Listing Images ===================
    path('listings/<int:listing_id>/images/', views.ListingImageCreateView.as_view(), name='listing-image-create'),
    path('listings/<int:listing_id>/images/<int:pk>/', views.ListingImageUpdateView.as_view(), name='listing-image-update'),
    path('listings/<int:listing_id>/images/<int:pk>/delete/', views.ListingImageDeleteView.as_view(), name='listing-image-delete'),
    path('listings/<int:listing_id>/images/<int:pk>/set-primary/', views.set_primary_image, name='listing-image-set-primary'),
    
    # =================== Search and Filters ===================
    path('search/', views.search_products, name='search'),
    path('search/filters/options/', views.filter_options, name='search-filter-options'),
    path('search/featured/', views.featured_listings, name='search-featured'),
    path('search/recent/', views.recent_listings, name='search-recent'),
]