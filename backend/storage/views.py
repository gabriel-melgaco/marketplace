import uuid
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.conf import settings
from .minio_client import get_minio_client
from .serializers import PresignedUrlSerializer, PresignedUrlResponseSerializer
from drf_spectacular.utils import extend_schema, OpenApiResponse


#For Documentation
@extend_schema(
    request=PresignedUrlSerializer,
    responses={
        200: PresignedUrlResponseSerializer,
        401: OpenApiResponse(description="Não autenticado"),
    },
    tags=["Uploads"]
)

class GeneratePresignedUrlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PresignedUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_name = serializer.validated_data["file_name"]
        content_type = serializer.validated_data["content_type"]

        extension = file_name.split(".")[-1]
        object_name = f"products/{uuid.uuid4()}.{extension}"

        client = get_minio_client()

        url = client.presigned_put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_name,
            expires=timedelta(minutes=10),
        )

        return Response({
            "upload_url": url,
            "object_name": object_name,
            "file_url": f"http://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_name}"
        })
