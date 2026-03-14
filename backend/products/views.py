from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db.models import Q, Min, Max, Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from storage.minio_client import delete_object
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter, OpenApiResponse, OpenApiTypes
from rest_framework import serializers as rf_serializers

from .models import (
    Category, Series, Products, Brand,
    Condition, MarketplaceListing, MarketplaceListingImages, ListingPackage,
)
from .serializers import (
    CategorySerializer, SeriesSerializer, ProductSerializer,
    BrandSerializer, ConditionSerializer,
    MarketplaceListingSerializer, MarketplaceListingCreateSerializer,
    MarketplaceListingUpdateSerializer, MarketplaceListingDetailSerializer,
    MarketplaceListingImageSerializer, MarketplaceListingImageCreateSerializer,
    ListingPackageSerializer,
)


# =================== Category Views ===================
@extend_schema(
    tags=['Products'],
    summary='List categories',
    description='List all active top-level categories with their children (hierarchical structure).'
)
class CategoryListView(generics.ListAPIView):
    """Listar todas as categorias ativas com hierarquia"""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Category.objects.filter(
            is_active=True,
            parent__isnull=True  # Apenas categorias principais
        ).prefetch_related('children')


@extend_schema(
    tags=['Products'],
    summary='Get category details',
    description='Get detailed information about a specific category by slug.'
)
class CategoryDetailView(generics.RetrieveAPIView):
    """Detalhes de uma categoria específica"""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    
    def get_queryset(self):
        return Category.objects.filter(is_active=True)


@extend_schema(
    tags=['Products'],
    summary='List products in category',
    description='List all products in a category (including products from subcategories).'
)
class CategoryProductsView(generics.ListAPIView):
    """Produtos de uma categoria"""
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        slug = self.kwargs.get('slug')
        category = get_object_or_404(Category, slug=slug, is_active=True)
        
        # Inclui produtos da categoria e suas subcategorias
        categories = [category]
        categories.extend(category.children.filter(is_active=True))
        
        return Products.objects.filter(
            category__in=categories
        ).select_related('category', 'series')


# =================== Series Views ===================
@extend_schema(tags=['Products'], summary='List series', description='List all product series.')
class SeriesListView(generics.ListAPIView):
    """Listar todas as séries"""
    queryset = Series.objects.all()
    serializer_class = SeriesSerializer
    permission_classes = [AllowAny]


@extend_schema(tags=['Products'], summary='Get series details', description='Get detailed information about a specific series by slug.')
class SeriesDetailView(generics.RetrieveAPIView):
    """Detalhes de uma série específica"""
    queryset = Series.objects.all()
    serializer_class = SeriesSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


@extend_schema(tags=['Products'], summary='List products in series', description='List all products in a specific series.')
class SeriesProductsView(generics.ListAPIView):
    """Produtos de uma série"""
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        slug = self.kwargs.get('slug')
        return Products.objects.filter(
            series__slug=slug
        ).select_related('category', 'series')


# =================== Product Views ===================
@extend_schema(
    tags=['Products'],
    summary='List products',
    description='List all products with filtering, search, and ordering capabilities.'
)
class ProductListView(generics.ListAPIView):
    """Listar todos os produtos com filtros e paginação"""
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category__slug', 'series__slug']
    search_fields = ['name', 'description', 'code']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        return Products.objects.all().select_related('category', 'series')


@extend_schema(tags=['Products'], summary='Get product details', description='Get detailed information about a specific product by slug.')
class ProductDetailView(generics.RetrieveAPIView):
    """Detalhes de um produto específico"""
    queryset = Products.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


@extend_schema(tags=['Products'], summary='List product listings', description='List all active marketplace listings for a specific product.')
class ProductListingsView(generics.ListAPIView):
    """Listagens disponíveis de um produto"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        slug = self.kwargs.get('slug')
        return MarketplaceListing.objects.filter(
            product__slug=slug,
            is_active=True,
            quantity__gt=0
        ).select_related('product', 'product__category', 'brand', 'condition', 'seller', 'shipping_address').prefetch_related('images')


# =================== Brand Views ===================
@extend_schema(tags=['Products'], summary='List brands', description='List all active brands.')
class BrandListView(generics.ListAPIView):
    """Listar todas as marcas ativas"""
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


@extend_schema(tags=['Products'], summary='Get brand details', description='Get detailed information about a specific brand by slug.')
class BrandDetailView(generics.RetrieveAPIView):
    """Detalhes de uma marca"""
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


@extend_schema(tags=['Products'], summary='List brand listings', description='List all active marketplace listings for a specific brand.')
class BrandListingsView(generics.ListAPIView):
    """Listagens de uma marca"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        slug = self.kwargs.get('slug')
        return MarketplaceListing.objects.filter(
            brand__slug=slug,
            is_active=True
        ).select_related('product', 'product__category', 'brand', 'condition', 'seller', 'shipping_address').prefetch_related('images')


# =================== Condition Views ===================
@extend_schema(tags=['Products'], summary='List conditions', description='List all available product conditions (new, used, etc).')
class ConditionListView(generics.ListAPIView):
    """Listar todas as condições disponíveis"""
    queryset = Condition.objects.all()
    serializer_class = ConditionSerializer
    permission_classes = [AllowAny]
    pagination_class = None


# =================== Marketplace Listing Views ===================
@extend_schema(
    tags=['Products'],
    summary='List marketplace listings',
    description='List all active marketplace listings with advanced filtering and ordering. Supports price range filters.'
)
class MarketplaceListingListView(generics.ListAPIView):
    """Listar todas as listagens ativas com filtros avançados"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['brand__slug', 'condition__slug', 'product__category__slug']
    ordering_fields = ['price', 'created_at', 'views_count']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = MarketplaceListing.objects.filter(
            is_active=True, sold_at=None,
            quantity__gt=0
        ).select_related('product', 'product__category', 'brand', 'condition', 'seller', 'shipping_address').prefetch_related('images')

        # Filtros customizados
        price_min = self.request.query_params.get('price_min')
        price_max = self.request.query_params.get('price_max')

        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        if price_max:
            queryset = queryset.filter(price__lte=price_max)

        return queryset


@extend_schema(tags=['Products'], summary='Get listing details', description='Get detailed information about a specific marketplace listing.')
class MarketplaceListingDetailView(generics.RetrieveAPIView):
    """Detalhes de uma listagem específica"""
    queryset = MarketplaceListing.objects.filter(is_active=True)
    serializer_class = MarketplaceListingDetailSerializer
    permission_classes = [AllowAny]


@extend_schema(
    tags=['Products'],
    summary='Create listing',
    description=(
        'Create a new marketplace listing. Authenticated sellers only.\n\n'
        '**Prerequisites:**\n'
        '- Seller must have a connected Melhor Envio account '
        '(`GET /api/logistics/me/connect/`).\n\n'
        '**Shipping address:** automatically assigned from the seller\'s connected '
        'Melhor Envio account. No need to provide `shipping_address` in the request.\n\n'
        '**`shipping_method` field:**\n'
        '- `"in_person"` — product only accepts in-person pickup. '
        'Melhor Envio shipping quotes and shipment creation will be blocked for this listing.\n'
        '- `"melhor_envio"` — product only accepts carrier delivery via Melhor Envio. '
        'In-person delivery will be blocked at order creation.\n'
        '- `"both"` (default) — both methods are accepted.'
    ),
)
class MarketplaceListingCreateView(generics.CreateAPIView):
    """Criar nova listagem"""
    serializer_class = MarketplaceListingCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        user = self.request.user
        if not user.stripe_account_id:
            raise PermissionDenied(
                'É necessário conectar uma conta Stripe antes de criar um anúncio. '
                'Acesse POST /api/payments/connect/create/ para configurar sua conta.'
            )
        if not user.seller_verified:
            raise PermissionDenied(
                'Sua conta Stripe Connect ainda não está ativa. '
                'Complete o onboarding em POST /api/payments/connect/onboarding-link/ '
                'e aguarde a ativação.'
            )
        listing = serializer.save(seller=self.request.user, is_active=True)
        try:
            from notifications.services.notification_service import NotificationService
            from notifications.models import NotificationType
            NotificationService.notify(
                recipient=self.request.user,
                event_type=NotificationType.LISTING_CREATED,
                title=f'Anúncio publicado: {listing.title}',
                body=f'Seu anúncio "{listing.title}" foi publicado com sucesso.',
                metadata={'listing_id': listing.id, 'listing_title': listing.title},
                idempotency_key=f'listing_created_{listing.id}',
            )
        except Exception:
            pass

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Check if any package exceeds 30kg and warn the seller
        packages = request.data.get('packages', [])
        if any(
            float(pkg.get('weight_kg', 0)) > 30
            for pkg in packages
            if isinstance(pkg, dict)
        ):
            response.data['warning'] = (
                "Este produto possui um ou mais pacotes acima de 30kg. A maioria das "
                "transportadoras não aceita encomendas acima desse peso. Recomendamos que a "
                "entrega seja realizada presencialmente (in-person)."
            )
        return response


@extend_schema(tags=['Products'], summary='List my listings', description='List all marketplace listings created by the authenticated seller.')
class MyListingsView(generics.ListAPIView):
    """Minhas listagens (vendedor autenticado)"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MarketplaceListing.objects.filter(
            seller=self.request.user
        ).select_related('product', 'product__category', 'brand', 'condition', 'shipping_address').prefetch_related('images', 'packages')


@extend_schema(tags=['Products'], summary='Update listing', description='Update a marketplace listing. Only the seller who created it can update.')
class MarketplaceListingUpdateView(generics.UpdateAPIView):
    """Atualizar listagem"""
    serializer_class = MarketplaceListingUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MarketplaceListing.objects.filter(seller=self.request.user)


@extend_schema(tags=['Products'], summary='Delete listing', description='Delete a marketplace listing. Only the seller who created it can delete.', request=None, responses={204: None})
class MarketplaceListingDeleteView(generics.UpdateAPIView):
    """Desativar listagem (soft delete)"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['delete']

    def get_queryset(self):
        return MarketplaceListing.objects.filter(seller=self.request.user, is_active=True)

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=['Products'],
    summary='Increment view count',
    description='Increment the view counter for a marketplace listing.',
    request=None,
    responses={
        200: inline_serializer(
            name='IncrementViewResponse',
            fields={'views_count': rf_serializers.IntegerField()}
        )
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def increment_view_count(request, pk):
    """Incrementar contador de visualizações"""
    listing = get_object_or_404(MarketplaceListing, pk=pk, is_active=True)
    listing.views_count += 1
    listing.save(update_fields=['views_count'])
    return Response({'views_count': listing.views_count})


@extend_schema(
    tags=['Products'],
    summary='Block a listing (admin)',
    description='Admin action: deactivates a marketplace listing and notifies the seller.',
    request=None,
    responses={
        200: inline_serializer(
            name='BlockListingResponse',
            fields={
                'is_active': rf_serializers.BooleanField(),
                'message': rf_serializers.CharField(),
            }
        ),
    }
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def block_listing(request, pk):
    """Admin blocks a listing and notifies the seller."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    listing = get_object_or_404(MarketplaceListing, pk=pk)
    if not listing.is_active:
        return Response({'is_active': False, 'message': 'Listing already inactive'})
    listing.is_active = False
    listing.save(update_fields=['is_active'])
    try:
        from notifications.services.notification_service import NotificationService
        from notifications.models import NotificationType
        NotificationService.notify(
            recipient=listing.seller,
            event_type=NotificationType.LISTING_BLOCKED,
            title=f'Anúncio bloqueado: {listing.title}',
            body=(
                f'Seu anúncio "{listing.title}" foi bloqueado por um administrador. '
                'Entre em contato com o suporte para mais informações.'
            ),
            metadata={'listing_id': listing.id, 'listing_title': listing.title},
            idempotency_key=f'listing_blocked_{listing.id}',
        )
    except Exception as _exc:
        _log.warning('listing_blocked notification failed: %s', _exc)
    return Response({'is_active': False, 'message': 'Listing blocked successfully.'})


@extend_schema(
    tags=['Products'],
    summary='Toggle listing active status',
    description='Activate or deactivate a marketplace listing.',
    request=None,
    responses={
        200: inline_serializer(
            name='ToggleActiveResponse',
            fields={'is_active': rf_serializers.BooleanField()}
        )
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_listing_active(request, pk):
    """Ativar/desativar listagem"""
    listing = get_object_or_404(MarketplaceListing, pk=pk, seller=request.user)
    listing.is_active = not listing.is_active
    listing.save(update_fields=['is_active'])
    return Response({'is_active': listing.is_active})


@extend_schema(
    tags=['Products'],
    summary='Mark listing as sold',
    description='Mark one unit as sold. If only 1 item left, deactivates listing and sets sold_at. Otherwise decrements quantity by 1.',
    request=None,
    responses={
        200: inline_serializer(
            name='MarkAsSoldResponse',
            fields={'message': rf_serializers.CharField()}
        ),
        400: OpenApiResponse(description='Listing is inactive or has no stock')
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_sold(request, pk):
    """Marcar como vendido. Caso anúncio desativado retorna 400. Caso haja uma quantidade maior ou igual a 2 (dois) itens à venda, o endpoint apenas fará o decréscimo de 1 (um) item. Caso haja apenas 1(um) item, irá desativar o listing, preencher o sold_at e igualar a quantidade a '0'."""
    listing = get_object_or_404(
        MarketplaceListing,
        pk=pk,
        seller=request.user
    )

    # Anúncio inativo
    if not listing.is_active:
        return Response(
            {'detail': 'Este anúncio já está inativo.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Sem estoque
    if listing.quantity <= 0:
        return Response(
            {'detail': 'Este anúncio não possui estoque disponível.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Reduz estoque
    listing.quantity -= 1

    # Última unidade vendida
    if listing.quantity == 0:
        listing.is_active = False
        listing.sold_at = timezone.now()

    listing.save(update_fields=['quantity', 'is_active', 'sold_at'])

    return Response(
        {'message': 'Venda registrada com sucesso.'},
        status=status.HTTP_200_OK
    )


# =================== Listing Images Views ===================
@extend_schema(tags=['Products'], summary='Upload listing image', description='Upload an image for a marketplace listing.')
class ListingImageCreateView(generics.CreateAPIView):
    """Upload de imagem"""
    serializer_class = MarketplaceListingImageCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        listing_id = self.kwargs.get('listing_id')
        listing = get_object_or_404(MarketplaceListing, pk=listing_id, seller=self.request.user)
        serializer.save(listing=listing)


@extend_schema(tags=['Products'], summary='Update listing image', description='Update listing image order or primary flag.')
class ListingImageUpdateView(generics.UpdateAPIView):
    """Atualizar ordem/primary"""
    serializer_class = MarketplaceListingImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        listing_id = self.kwargs.get('listing_id')
        return MarketplaceListingImages.objects.filter(
            listing_id=listing_id,
            listing__seller=self.request.user
        )


@extend_schema(tags=['Products'], summary='Delete listing image', description='Delete a listing image from storage and database.', request=None, responses={204: None})
class ListingImageDeleteView(generics.DestroyAPIView):
    """Deletar imagem"""
    serializer_class = MarketplaceListingImageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        listing_id = self.kwargs.get('listing_id')
        image_id = self.kwargs.get('pk')

        return get_object_or_404(
            MarketplaceListingImages,
            pk=image_id,
            listing_id=listing_id,
            listing__seller=self.request.user
        )

    def perform_destroy(self, instance):
        # Deleta do MinIO
        delete_object(instance.object_name)

        #Deleta do banco
        instance.delete()


@extend_schema(
    tags=['Products'],
    summary='Set primary image',
    description='Set a specific image as the primary image for a marketplace listing.',
    request=None,
    responses={
        200: inline_serializer(
            name='SetPrimaryImageResponse',
            fields={'message': rf_serializers.CharField()}
        )
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_primary_image(request, listing_id, pk):
    """Definir como principal"""
    # Remove primary de todas as imagens da listagem
    MarketplaceListingImages.objects.filter(
        listing_id=listing_id,
        listing__seller=request.user
    ).update(is_primary=False)

    # Define a imagem como primary
    image = get_object_or_404(
        MarketplaceListingImages,
        pk=pk,
        listing_id=listing_id,
        listing__seller=request.user
    )
    image.is_primary = True
    image.save(update_fields=['is_primary'])

    return Response({'message': 'Imagem definida como principal'})


# =================== Search and Filter Views ===================
@extend_schema(
    tags=['Products'],
    summary='Search products',
    description='Search marketplace listings by product name, description, or brand. Returns up to 20 results.',
    parameters=[
        OpenApiParameter(name='q', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, description='Search query')
    ],
    responses={
        200: inline_serializer(
            name='SearchProductsResponse',
            fields={'results': MarketplaceListingSerializer(many=True)}
        )
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def search_products(request):
    """Busca geral por nome, descrição e marca de produtos"""
    query = request.query_params.get('q', '')

    if not query:
        return Response({'results': []})

    listings = MarketplaceListing.objects.filter(
        Q(product__name__icontains=query) |
        Q(product__description__icontains=query) |
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(brand__name__icontains=query),
        is_active=True, sold_at=None
    ).select_related('product', 'product__category', 'brand', 'condition', 'shipping_address').prefetch_related('images')[:20]

    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response({'results': serializer.data})


@extend_schema(
    tags=['Products'],
    summary='Get filter options',
    description='Get available filter options including categories, brands, conditions, and price range.',
    responses={
        200: inline_serializer(
            name='FilterOptionsResponse',
            fields={
                'categories': CategorySerializer(many=True),
                'brands': BrandSerializer(many=True),
                'conditions': ConditionSerializer(many=True),
                'price_range': rf_serializers.DictField()
            }
        )
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def filter_options(request):
    """Retorna opções para filtros"""
    price_range = MarketplaceListing.objects.filter(
        is_active=True
    ).aggregate(Min('price'), Max('price'))

    return Response({
        'categories': CategorySerializer(Category.objects.filter(is_active=True), many=True).data,
        'brands': BrandSerializer(Brand.objects.filter(is_active=True), many=True).data,
        'conditions': ConditionSerializer(Condition.objects.all(), many=True).data,
        'price_range': {
            'min': price_range['price__min'] or 0,
            'max': price_range['price__max'] or 0
        }
    })


@extend_schema(
    tags=['Products'],
    summary='Get featured listings',
    description='Get top 10 featured listings (most viewed).',
    responses={200: MarketplaceListingSerializer(many=True)}
)
@api_view(['GET'])
@permission_classes([AllowAny])
def featured_listings(request):
    """Listagens em destaque (mais visualizadas)"""
    listings = MarketplaceListing.objects.filter(
        is_active=True, sold_at=None,
        quantity__gt=0
    ).order_by('-views_count')[:10].select_related(
        'product', 'product__category', 'brand', 'condition', 'seller', 'shipping_address'
    ).prefetch_related('images')

    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=['Products'],
    summary='Get recent listings',
    description='Get the 20 most recently created active listings.',
    responses={200: MarketplaceListingSerializer(many=True)}
)
@api_view(['GET'])
@permission_classes([AllowAny])
def recent_listings(request):
    """Listagens recentes"""
    listings = MarketplaceListing.objects.filter(
        is_active=True,
        quantity__gt=0
    ).order_by('-created_at')[:20].select_related(
        'product', 'product__category', 'brand', 'condition', 'seller', 'shipping_address'
    ).prefetch_related('images')

    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response(serializer.data)


# =================== Listing Package Views ===================
@extend_schema(
    tags=['Products'],
    summary='List / add packages for a listing',
    description=(
        'GET: List all packages of a marketplace listing.\n\n'
        'POST: Add a new package to an existing listing. '
        'Only the seller who owns the listing can add packages.'
    ),
    responses={200: ListingPackageSerializer(many=True)},
)
class ListingPackageListView(generics.ListCreateAPIView):
    """
    GET  /api/products/listings/<listing_id>/packages/ — lista pacotes
    POST /api/products/listings/<listing_id>/packages/ — adiciona pacote
    """

    serializer_class = ListingPackageSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        listing_id = self.kwargs.get('listing_id')
        # For GET requests, anyone can view packages of a listing
        get_object_or_404(MarketplaceListing, pk=listing_id)
        return ListingPackage.objects.filter(listing_id=listing_id)

    def perform_create(self, serializer):
        listing_id = self.kwargs.get('listing_id')
        listing = get_object_or_404(
            MarketplaceListing, pk=listing_id, seller=self.request.user
        )
        serializer.save(listing=listing)


@extend_schema(
    tags=['Products'],
    summary='Retrieve / update / delete a listing package',
    description=(
        'Manage a single package of a marketplace listing.\n\n'
        'GET: Retrieve package details (public).\n'
        'PUT / PATCH: Update package dimensions (seller only).\n'
        'DELETE: Remove a package from the listing (seller only). '
        'Cannot delete the last package — a listing must always have at least one.'
    ),
)
class ListingPackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/products/listings/<listing_id>/packages/<pk>/ — detalhes
    PUT    /api/products/listings/<listing_id>/packages/<pk>/ — substituição completa
    PATCH  /api/products/listings/<listing_id>/packages/<pk>/ — atualização parcial
    DELETE /api/products/listings/<listing_id>/packages/<pk>/ — remoção
    """

    serializer_class = ListingPackageSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        listing_id = self.kwargs.get('listing_id')
        return ListingPackage.objects.filter(listing_id=listing_id)

    def get_object(self):
        listing_id = self.kwargs.get('listing_id')
        pk = self.kwargs.get('pk')

        if self.request.method == 'GET':
            # Any user can retrieve package details
            return get_object_or_404(ListingPackage, pk=pk, listing_id=listing_id)

        # Write operations: verify ownership
        return get_object_or_404(
            ListingPackage,
            pk=pk,
            listing_id=listing_id,
            listing__seller=self.request.user,
        )

    def perform_destroy(self, instance):
        """
        Impede a remoção do último pacote do listing.
        Um anúncio deve ter sempre pelo menos 1 pacote para que o cálculo de
        frete funcione corretamente.
        """
        remaining = ListingPackage.objects.filter(listing=instance.listing).count()
        if remaining <= 1:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                'Não é possível remover o último pacote do anúncio. '
                'O anúncio deve ter pelo menos 1 pacote com dimensões válidas.'
            )
        instance.delete()