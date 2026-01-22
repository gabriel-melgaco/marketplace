from rest_framework import serializers
from .models import (
    Category, Series, Products, Brand, 
    Condition, MarketplaceListing, MarketplaceListingImages
)


# =================== Category Serializers ===================
class CategoryChildrenSerializer(serializers.ModelSerializer):
    """Serializer para subcategorias"""
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class CategorySerializer(serializers.ModelSerializer):
    """Serializer completo de categoria com hierarquia"""
    children = CategoryChildrenSerializer(many=True, read_only=True)
    parent = serializers.StringRelatedField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'children', 'is_active']


class CategorySimpleSerializer(serializers.ModelSerializer):
    """Serializer simples de categoria"""
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


# =================== Series Serializers ===================
class SeriesSerializer(serializers.ModelSerializer):
    """Serializer completo de série"""
    class Meta:
        model = Series
        fields = '__all__'


class SeriesSimpleSerializer(serializers.ModelSerializer):
    """Serializer simples de série"""
    class Meta:
        model = Series
        fields = ['id', 'name', 'slug']


# =================== Brand Serializers ===================
class BrandSerializer(serializers.ModelSerializer):
    """Serializer completo de marca"""
    class Meta:
        model = Brand
        fields = '__all__'


class BrandSimpleSerializer(serializers.ModelSerializer):
    """Serializer simples de marca"""
    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo']


# =================== Condition Serializers ===================
class ConditionSerializer(serializers.ModelSerializer):
    """Serializer de condição"""
    class Meta:
        model = Condition
        fields = '__all__'


# =================== Product Serializers ===================
class ProductSerializer(serializers.ModelSerializer):
    """Serializer completo de produto"""
    category = CategorySimpleSerializer(read_only=True)
    series = SeriesSimpleSerializer(read_only=True)
    
    class Meta:
        model = Products
        fields = '__all__'


class ProductSimpleSerializer(serializers.ModelSerializer):
    """Serializer simples de produto"""
    class Meta:
        model = Products
        fields = ['id', 'name', 'slug', 'code']


# =================== Listing Images Serializers ===================
class MarketplaceListingImageSerializer(serializers.ModelSerializer):
    """Serializer de imagens de listagem"""
    class Meta:
        model = MarketplaceListingImages
        fields = '__all__'
        read_only_fields = ['created_at']


class MarketplaceListingImageCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar imagens"""
    class Meta:
        model = MarketplaceListingImages
        fields = ['image_url', 'object_name', 'is_primary', 'order']


# =================== Marketplace Listing Serializers ===================
class MarketplaceListingSerializer(serializers.ModelSerializer):
    """Serializer completo de listagem para listagem"""
    product = ProductSimpleSerializer(read_only=True)
    brand = BrandSimpleSerializer(read_only=True)
    condition = ConditionSerializer(read_only=True)
    images = MarketplaceListingImageSerializer(many=True, read_only=True)
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    
    class Meta:
        model = MarketplaceListing
        fields = [
            'id', 'product', 'seller', 'seller_name', 'price', 'brand', 
            'quantity', 'is_active', 'description', 'condition', 
            'views_count', 'weight_kg', 'height_cm', 'width_cm', 
            'length_cm', 'created_at', 'updated_at', 'sold_at', 
            'images', 'primary_image'
        ]
        read_only_fields = ['seller', 'views_count', 'created_at', 'updated_at', 'sold_at']
    
    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first()
        if primary:
            return primary.image_url
        first_image = obj.images.first()
        return first_image.image_url if first_image else None


class MarketplaceListingCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar listagem"""
    class Meta:
        model = MarketplaceListing
        fields = [
            'product', 'price', 'brand', 'quantity', 
            'description', 'condition', 'weight_kg', 
            'height_cm', 'width_cm', 'length_cm'
        ]
    
    def create(self, validated_data):
        # O seller será adicionado na view
        return super().create(validated_data)


class MarketplaceListingUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar listagem"""
    class Meta:
        model = MarketplaceListing
        fields = [
            'price', 'quantity', 'description', 
            'weight_kg', 'height_cm', 'width_cm', 'length_cm'
        ]


class MarketplaceListingDetailSerializer(serializers.ModelSerializer):
    """Serializer detalhado de listagem"""
    product = ProductSerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    condition = ConditionSerializer(read_only=True)
    images = MarketplaceListingImageSerializer(many=True, read_only=True)
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    
    class Meta:
        model = MarketplaceListing
        fields = '__all__'