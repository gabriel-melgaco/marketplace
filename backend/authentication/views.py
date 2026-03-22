# authentication/views.py

from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiResponse,
    OpenApiExample,
)

from .serializers import CustomUserSerializer, LoginResponseSerializer
from auth_kit.views.login import LoginView as BaseLoginView


User = get_user_model()


@extend_schema_view(
    get=extend_schema(
        tags=["Authentication"],
        operation_id="auth_user_retrieve",
        summary="Retrieve authenticated user profile",
        description="""
Return the full profile of the currently authenticated user.

**Authentication**: Required (JWT Bearer token via `Authorization` header or `jwt-auth` cookie)

**Permissions**: Authenticated users only
        """,
        responses={
            200: CustomUserSerializer,
            401: OpenApiResponse(description="Authentication credentials were not provided or are invalid."),
        },
        examples=[
            OpenApiExample(
                name="User profile response",
                value={
                    "id": 1,
                    "email": "joao.silva@email.com",
                    "full_name": "Joao Silva",
                    "birthday": "1990-05-15",
                    "cpf": "12345678909",
                    "picture": "https://cdn.example.com/avatars/joao.jpg",
                    "is_active": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    ),
    put=extend_schema(
        tags=["Authentication"],
        operation_id="auth_user_update",
        summary="Full update of authenticated user profile",
        description="""
Replace all editable fields on the authenticated user's profile.

All fields are required. Use `PATCH` for partial updates.

**Authentication**: Required (JWT Bearer token via `Authorization` header or `jwt-auth` cookie)

**Permissions**: Authenticated users only

**Validation rules**:
- `full_name`: must contain at least two words and be at least 8 characters.
- `cpf`: must be a valid Brazilian CPF (11 digits) or CNPJ (14 digits), digits only. Must be unique.
        """,
        request=CustomUserSerializer,
        responses={
            200: CustomUserSerializer,
            400: OpenApiResponse(description="Validation error — invalid field values."),
            401: OpenApiResponse(description="Authentication credentials were not provided or are invalid."),
        },
        examples=[
            OpenApiExample(
                name="Update profile request",
                value={
                    "email": "joao.silva@email.com",
                    "full_name": "Joao Silva",
                    "birthday": "1990-05-15",
                    "cpf": "12345678909",
                    "picture": "https://cdn.example.com/avatars/joao.jpg",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Update profile response",
                value={
                    "id": 1,
                    "email": "joao.silva@email.com",
                    "full_name": "Joao Silva",
                    "birthday": "1990-05-15",
                    "cpf": "12345678909",
                    "picture": "https://cdn.example.com/avatars/joao.jpg",
                    "is_active": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                name="Validation error — invalid CPF",
                value={
                    "cpf": ["CPF invalido."],
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    ),
    patch=extend_schema(
        tags=["Authentication"],
        operation_id="auth_user_partial_update",
        summary="Partial update of authenticated user profile",
        description="""
Update one or more fields on the authenticated user's profile without requiring all fields.

**Authentication**: Required (JWT Bearer token via `Authorization` header or `jwt-auth` cookie)

**Permissions**: Authenticated users only

**Validation rules**:
- `full_name`: must contain at least two words and be at least 8 characters.
- `cpf`: must be a valid Brazilian CPF (11 digits) or CNPJ (14 digits), digits only. Must be unique.
        """,
        request=CustomUserSerializer,
        responses={
            200: CustomUserSerializer,
            400: OpenApiResponse(description="Validation error — invalid field values."),
            401: OpenApiResponse(description="Authentication credentials were not provided or are invalid."),
        },
        examples=[
            OpenApiExample(
                name="Partial update — change picture only",
                value={
                    "picture": "https://cdn.example.com/avatars/new-photo.jpg",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Partial update response",
                value={
                    "id": 1,
                    "email": "joao.silva@email.com",
                    "full_name": "Joao Silva",
                    "birthday": "1990-05-15",
                    "cpf": "12345678909",
                    "picture": "https://cdn.example.com/avatars/new-photo.jpg",
                    "is_active": True,
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    ),
)
class CustomUserView(RetrieveUpdateAPIView):
    """View de User customizada que retorna os dados completos modificados do usuario"""

    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        operation_id="auth_login",
        summary="User login",
        description="""
Authenticate a user with email and password. Returns JWT access and refresh tokens alongside
the full user profile.

**Authentication**: Not required

**Permissions**: Public

Tokens are returned both in the response body and set as `HttpOnly` cookies (`jwt-auth` and
`jwt-auth-refresh`). The `refresh` field in the response body is intentionally blanked when
cookies are used — the actual refresh token is stored in the `jwt-auth-refresh` cookie.

Use the `access` token in the `Authorization: Bearer <token>` header for subsequent requests,
or rely on the cookie if your client sends credentials.
        """,
        request=None,  # auth_kit uses a dynamically generated serializer; doc via examples below
        responses={
            200: LoginResponseSerializer,
            400: OpenApiResponse(description="Invalid credentials or missing required fields."),
        },
        examples=[
            OpenApiExample(
                name="Login request",
                value={
                    "email": "joao.silva@email.com",
                    "password": "mysecretpassword",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Successful login response",
                value={
                    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh": "",
                    "access_expiration": "2026-03-22T18:00:00Z",
                    "refresh_expiration": "2026-03-29T12:00:00Z",
                    "user": {
                        "id": 1,
                        "email": "joao.silva@email.com",
                        "full_name": "Joao Silva",
                        "birthday": "1990-05-15",
                        "cpf": "12345678909",
                        "picture": "https://cdn.example.com/avatars/joao.jpg",
                        "is_active": True,
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                name="Invalid credentials error",
                value={
                    "non_field_errors": ["Unable to log in with provided credentials."],
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
)
class CustomLoginView(BaseLoginView):
    """View de login customizada que retorna os dados completos do usuario"""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            email = request.data.get("email") or request.data.get("username")
            user = User.objects.get(email=email)

            user_serializer = CustomUserSerializer(user)

            response.data["user"] = user_serializer.data

        return response
