from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from .views import marketplace_fee


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('authentication.urls')),
    path('api/storage/', include('storage.urls')),
    path('api/products/', include('products.urls')),
    path('api/logistics/', include('logistics.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/config/marketplace/fee/', marketplace_fee, name='marketplace-fee'),
    path('accounts/', include('allauth.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]


