from django.urls import path
from .views import GeneratePresignedUrlView

urlpatterns = [
    path("upload/presigned-url/", GeneratePresignedUrlView.as_view()),
]
