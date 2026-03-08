from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings
from drf_spectacular.utils import extend_schema


@extend_schema(
    summary="Taxa de comissão da plataforma",
    description="Retorna a porcentagem de comissão cobrada pela plataforma sobre o valor dos produtos.",
    responses={200: {"type": "object", "properties": {"platform_fee_percentage": {"type": "integer", "example": 10}}}},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def marketplace_fee(request):
    return Response({
        "platform_fee_percentage": getattr(settings, 'PLATFORM_FEE_PERCENTAGE', 10),
    })
