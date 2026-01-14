from django.urls import include, path
from authentication.views import CustomUserView, CustomLoginView


urlpatterns = [
    path("auth/user/", CustomUserView.as_view(), name="custom-user"),
    path('auth/login/', CustomLoginView.as_view(), name='custom-login'),
    path('auth/', include('auth_kit.urls')),
    path('auth/social/', include('auth_kit.social.urls')),
]