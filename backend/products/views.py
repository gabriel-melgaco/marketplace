from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db.models import Q, Min, Max, Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from storage.minio_client import delete_object

from .models import (
    Category, Series, Products, Brand, 
    Condition, MarketplaceListing, MarketplaceListingImages
)
from .serializers import (
    CategorySerializer, SeriesSerializer, ProductSerializer,
    BrandSerializer, ConditionSerializer, 
    MarketplaceListingSerializer, MarketplaceListingCreateSerializer,
    MarketplaceListingUpdateSerializer, MarketplaceListingDetailSerializer,
    MarketplaceListingImageSerializer, MarketplaceListingImageCreateSerializer
)


# =================== Category Views ===================
class CategoryListView(generics.ListAPIView):
    """Listar todas as categorias ativas com hierarquia"""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        return Category.objects.filter(
            is_active=True,
            parent__isnull=True  # Apenas categorias principais
        ).prefetch_related('children')


class CategoryDetailView(generics.RetrieveAPIView):
    """Detalhes de uma categoria específica"""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    
    def get_queryset(self):
        return Category.objects.filter(is_active=True)


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
class SeriesListView(generics.ListAPIView):
    """Listar todas as séries"""
    queryset = Series.objects.all()
    serializer_class = SeriesSerializer
    permission_classes = [AllowAny]


class SeriesDetailView(generics.RetrieveAPIView):
    """Detalhes de uma série específica"""
    queryset = Series.objects.all()
    serializer_class = SeriesSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


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


class ProductDetailView(generics.RetrieveAPIView):
    """Detalhes de um produto específico"""
    queryset = Products.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


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
        ).select_related('product', 'brand', 'condition', 'seller').prefetch_related('images')


# =================== Brand Views ===================
class BrandListView(generics.ListAPIView):
    """Listar todas as marcas ativas"""
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


class BrandDetailView(generics.RetrieveAPIView):
    """Detalhes de uma marca"""
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    
    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


class BrandListingsView(generics.ListAPIView):
    """Listagens de uma marca"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        slug = self.kwargs.get('slug')
        return MarketplaceListing.objects.filter(
            brand__slug=slug,
            is_active=True
        ).select_related('product', 'brand', 'condition', 'seller').prefetch_related('images')


# =================== Condition Views ===================
class ConditionListView(generics.ListAPIView):
    """Listar todas as condições disponíveis"""
    queryset = Condition.objects.all()
    serializer_class = ConditionSerializer
    permission_classes = [AllowAny]


# =================== Marketplace Listing Views ===================
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
        ).select_related('product', 'brand', 'condition', 'seller').prefetch_related('images')
        
        # Filtros customizados
        price_min = self.request.query_params.get('price_min')
        price_max = self.request.query_params.get('price_max')
        
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        if price_max:
            queryset = queryset.filter(price__lte=price_max)
        
        return queryset


class MarketplaceListingDetailView(generics.RetrieveAPIView):
    """Detalhes de uma listagem específica"""
    queryset = MarketplaceListing.objects.filter(is_active=True)
    serializer_class = MarketplaceListingDetailSerializer
    permission_classes = [AllowAny]


class MarketplaceListingCreateView(generics.CreateAPIView):
    """Criar nova listagem"""
    serializer_class = MarketplaceListingCreateSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, is_active=True)


class MyListingsView(generics.ListAPIView):
    """Minhas listagens (vendedor autenticado)"""
    serializer_class = MarketplaceListingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MarketplaceListing.objects.filter(
            seller=self.request.user
        ).select_related('product', 'brand', 'condition').prefetch_related('images')


class MarketplaceListingUpdateView(generics.UpdateAPIView):
    """Atualizar listagem"""
    serializer_class = MarketplaceListingUpdateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MarketplaceListing.objects.filter(seller=self.request.user)


class MarketplaceListingDeleteView(generics.DestroyAPIView):
    """Deletar listagem"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MarketplaceListing.objects.filter(seller=self.request.user)


@api_view(['POST'])
@permission_classes([AllowAny])
def increment_view_count(request, pk):
    """Incrementar contador de visualizações"""
    listing = get_object_or_404(MarketplaceListing, pk=pk, is_active=True)
    listing.views_count += 1
    listing.save(update_fields=['views_count'])
    return Response({'views_count': listing.views_count})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_listing_active(request, pk):
    """Ativar/desativar listagem"""
    listing = get_object_or_404(MarketplaceListing, pk=pk, seller=request.user)
    listing.is_active = not listing.is_active
    listing.save(update_fields=['is_active'])
    return Response({'is_active': listing.is_active})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_sold(request, pk):
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
class ListingImageCreateView(generics.CreateAPIView):
    """Upload de imagem"""
    serializer_class = MarketplaceListingImageCreateSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        listing_id = self.kwargs.get('listing_id')
        listing = get_object_or_404(MarketplaceListing, pk=listing_id, seller=self.request.user)
        serializer.save(listing=listing)


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


class ListingImageDeleteView(generics.DestroyAPIView):
    """Deletar imagem"""
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
        Q(description__icontains=query) |
        Q(brand__name__icontains=query),
        is_active=True, sold_at=None
    ).select_related('product', 'brand', 'condition').prefetch_related('images')[:20]
    
    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response({'results': serializer.data})


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


@api_view(['GET'])
@permission_classes([AllowAny])
def featured_listings(request):
    """Listagens em destaque (mais visualizadas)"""
    listings = MarketplaceListing.objects.filter(
        is_active=True, sold_at=None,
        quantity__gt=0
    ).order_by('-views_count')[:10].select_related(
        'product', 'brand', 'condition', 'seller'
    ).prefetch_related('images')
    
    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def recent_listings(request):
    """Listagens recentes"""
    listings = MarketplaceListing.objects.filter(
        is_active=True,
        quantity__gt=0
    ).order_by('-created_at')[:20].select_related(
        'product', 'brand', 'condition', 'seller'
    ).prefetch_related('images')
    
    serializer = MarketplaceListingSerializer(listings, many=True)
    return Response(serializer.data)