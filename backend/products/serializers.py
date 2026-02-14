from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    Category, Series, Products, Brand,
    Condition, MarketplaceListing, MarketplaceListingImages
)
from logistics.models import Address
from logistics.serializers import AddressSerializer
from authentication.models import CustomUser

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
    shipping_address = AddressSerializer(read_only=True)

    class Meta:
        model = MarketplaceListing
        fields = [
            'id', 'product', 'seller', 'seller_name', 'title', 'price', 'brand',
            'quantity', 'is_active', 'description', 'condition',
            'views_count', 'weight_kg', 'height_cm', 'width_cm',
            'length_cm', 'created_at', 'updated_at', 'sold_at',
            'images', 'primary_image', 'shipping_address'
        ]
        read_only_fields = ['seller', 'views_count', 'created_at', 'updated_at', 'sold_at']

    @extend_schema_field(serializers.URLField(allow_null=True))
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
            'product', 'title', 'price', 'brand', 'quantity',
            'description', 'condition', 'weight_kg',
            'height_cm', 'width_cm', 'length_cm', 'shipping_address'
        ]
    
    def validate_title(self, value):
        """Valida título do anúncio"""
        if len(value) < 5:
            raise serializers.ValidationError('O título deve ter pelo menos 5 caracteres.')
        return value

    def validate_price(self, value):
        """Valida valor mínimo de venda"""
        if value < 15:
            raise serializers.ValidationError('O valor mínimo de venda é de R$15,00')
        return value

    def validate_description(self, value):
        """Valida descrição mínima"""
        if len(value) < 30:
            raise serializers.ValidationError('Sua Descrição deve ter mais que 30 caracteres')
        return value
    
    def validate_quantity(self, value):
        """Valida quantidade em estoque"""
        if value <= 0:
            raise serializers.ValidationError('Você deve ter pelo menos 1(um) item a venda')
        return value
    
    def validate_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "O peso deve ser maior que zero."
            )
        return value

    def validate_height_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "A altura deve ser maior que zero."
            )
        return value

    def validate_width_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "A largura deve ser maior que zero."
            )
        return value

    def validate_length_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "O comprimento deve ser maior que zero."
            )
        return value

    def validate(self, data):
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                'Usuário não autenticado.'
            )

        user = request.user

        cpf = getattr(user, 'cpf', None)
        if not cpf:
            raise serializers.ValidationError(
                'Você precisa cadastrar um CPF válido antes de criar produtos.'
            )

        # Validate shipping_address
        shipping_address = data.get('shipping_address')
        if not shipping_address:
            raise serializers.ValidationError({
                'shipping_address': 'Endereço de envio é obrigatório.'
            })

        # Validate address belongs to user and is a shipping address
        if shipping_address.user != user:
            raise serializers.ValidationError({
                'shipping_address': 'Este endereço não pertence a você.'
            })

        if not shipping_address.is_shipping_address:
            raise serializers.ValidationError({
                'shipping_address': 'Este endereço não é um endereço de envio.'
            })

        if not shipping_address.is_active:
            raise serializers.ValidationError({
                'shipping_address': 'Este endereço está inativo.'
            })

        return data
    
    def create(self, validated_data):
        # O seller será adicionado na view
        return super().create(validated_data)


class MarketplaceListingUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar listagem"""
    class Meta:
        model = MarketplaceListing
        fields = [
            'title', 'price', 'quantity', 'description',
            'condition', 'weight_kg', 'height_cm',
            'width_cm', 'length_cm', 'is_active', 'shipping_address'
        ]

    def validate_title(self, value):
        if len(value) < 5:
            raise serializers.ValidationError('O título deve ter pelo menos 5 caracteres.')
        return value

    def validate_price(self, value):
        if value < 15:
            raise serializers.ValidationError('O valor mínimo de venda é de R$15,00')
        return value

    def validate_description(self, value):
        if len(value) < 30:
            raise serializers.ValidationError('Sua Descrição deve ter mais que 30 caracteres')
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError('Quantidade não pode ser negativa')
        return value

    def validate_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "O peso deve ser maior que zero."
            )
        return value

    def validate_height_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "A altura deve ser maior que zero."
            )
        return value

    def validate_width_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "A largura deve ser maior que zero."
            )
        return value

    def validate_length_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "O comprimento deve ser maior que zero."
            )
        return value

    def validate(self, data):
        """Valida endereço de envio se fornecido"""
        shipping_address = data.get('shipping_address')

        if shipping_address:
            request = self.context.get('request')
            if not request or not request.user.is_authenticated:
                raise serializers.ValidationError(
                    'Usuário não autenticado.'
                )

            user = request.user

            # Validate address belongs to user and is a shipping address
            if shipping_address.user != user:
                raise serializers.ValidationError({
                    'shipping_address': 'Este endereço não pertence a você.'
                })

            if not shipping_address.is_shipping_address:
                raise serializers.ValidationError({
                    'shipping_address': 'Este endereço não é um endereço de envio.'
                })

            if not shipping_address.is_active:
                raise serializers.ValidationError({
                    'shipping_address': 'Este endereço está inativo.'
                })

        return data


class MarketplaceListingDetailSerializer(serializers.ModelSerializer):
    """Serializer detalhado de listagem"""
    product = ProductSerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    condition = ConditionSerializer(read_only=True)
    images = MarketplaceListingImageSerializer(many=True, read_only=True)
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    shipping_address = AddressSerializer(read_only=True)

    class Meta:
        model = MarketplaceListing
        fields = '__all__'