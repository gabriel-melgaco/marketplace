import uuid
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.conf import settings
from .minio_client import get_internal_minio_client, get_public_minio_client, ensure_bucket_ready
from .serializers import PresignedUrlSerializer, PresignedUrlResponseSerializer
from drf_spectacular.utils import extend_schema, OpenApiResponse


from urllib.parse import urlparse, urlunparse
import uuid
from datetime import timedelta

class GeneratePresignedUrlView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PresignedUrlSerializer,
        responses={
            200: PresignedUrlResponseSerializer,
            401: OpenApiResponse(description="Não autenticado"),
        },
        tags=["Uploads"],
    )
    def post(self, request):
        serializer = PresignedUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_name = serializer.validated_data["file_name"]
        content_type = serializer.validated_data["content_type"]

        extension = file_name.rsplit(".", 1)[-1]
        object_name = f"products/{uuid.uuid4()}.{extension}"

        public_client = get_public_minio_client()

        upload_url = public_client.presigned_put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_name,
            expires=timedelta(minutes=10),
        )

        file_url = f"https://{settings.MINIO_PUBLIC_ENDPOINT}/{settings.MINIO_BUCKET}/{object_name}"

        return Response({
            "upload_url": upload_url,
            "object_name": object_name,
            "file_url": file_url,
        })