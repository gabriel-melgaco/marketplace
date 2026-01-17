from django.urls import path
from .views import GeneratePresignedUrlView

urlpatterns = [
    path("upload_image/presigned-url/", GeneratePresignedUrlView.as_view()),
]
