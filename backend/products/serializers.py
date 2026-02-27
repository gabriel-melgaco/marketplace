from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    Category, Series, Products, Brand,
    Condition, MarketplaceListing, MarketplaceListingImages,
    ListingPackage,
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
        fields = ['id', 'name', 'slug', 'code', 'image_url']


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


# =================== Listing Package Serializers ===================
class ListingPackageSerializer(serializers.ModelSerializer):
    """
    Serializer para pacotes de um anúncio (ListingPackage).

    Valida que todas as dimensões e peso são maiores que zero.
    Usado como nested serializer em criação/atualização de listings
    e como serializer standalone nos endpoints /packages/.
    """

    class Meta:
        model = ListingPackage
        fields = ['id', 'weight_kg', 'height_cm', 'width_cm', 'length_cm', 'description']
        read_only_fields = ['id']

    def validate_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError('O peso deve ser maior que zero.')
        return value

    def validate_height_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError('A altura deve ser maior que zero.')
        return value

    def validate_width_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError('A largura deve ser maior que zero.')
        return value

    def validate_length_cm(self, value):
        if value <= 0:
            raise serializers.ValidationError('O comprimento deve ser maior que zero.')
        return value


# =================== Marketplace Listing Serializers ===================
class MarketplaceListingSerializer(serializers.ModelSerializer):
    """Serializer completo de listagem para listagem"""
    product = ProductSimpleSerializer(read_only=True)
    brand = BrandSimpleSerializer(read_only=True)
    condition = ConditionSerializer(read_only=True)
    images = MarketplaceListingImageSerializer(many=True, read_only=True)
    packages = ListingPackageSerializer(many=True, read_only=True)
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
            'images', 'primary_image', 'packages', 'shipping_address'
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
    """
    Serializer para criar listagem.

    O campo `packages` é obrigatório e deve conter pelo menos 1 pacote com
    as dimensões físicas do produto. Os campos legados weight_kg / height_cm /
    width_cm / length_cm foram removidos da criação — use packages.
    """

    packages = ListingPackageSerializer(
        many=True,
        write_only=True,
        help_text='Lista de pacotes físicos do produto. Deve conter pelo menos 1 pacote.',
    )

    class Meta:
        model = MarketplaceListing
        fields = [
            'id', 'product', 'title', 'price', 'brand', 'quantity',
            'description', 'condition', 'packages',
        ]
        read_only_fields = ['id']

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

    def validate_packages(self, value):
        """Garante que ao menos 1 pacote seja fornecido."""
        if not value:
            raise serializers.ValidationError(
                'É necessário fornecer pelo menos 1 pacote com as dimensões do produto.'
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

        # Validate Melhor Envio connection and auto-assign shipping address
        from django.conf import settings as django_settings
        from logistics.models import SellerMelhorEnvioToken
        environment = 'sandbox' if getattr(django_settings, 'MELHOR_ENVIO_SANDBOX', True) else 'production'
        try:
            me_token = SellerMelhorEnvioToken.objects.get(
                seller=user,
                environment=environment,
                is_active=True,
            )
        except SellerMelhorEnvioToken.DoesNotExist:
            raise serializers.ValidationError(
                'Você precisa conectar uma conta do Melhor Envio antes de criar um anúncio. '
                'Acesse /api/logistics/me/connect/ para autorizar.'
            )

        if not me_token.me_address or not me_token.me_address.is_active:
            raise serializers.ValidationError(
                'Seu endereço de envio não foi sincronizado com a conta Melhor Envio. '
                'Reconecte sua conta em /api/logistics/me/connect/ para sincronizar.'
            )

        data['shipping_address'] = me_token.me_address
        return data

    def create(self, validated_data):
        """Cria o listing e seus pacotes em bulk dentro de uma única operação."""
        packages_data = validated_data.pop('packages')
        listing = super().create(validated_data)
        ListingPackage.objects.bulk_create([
            ListingPackage(listing=listing, **pkg) for pkg in packages_data
        ])
        return listing


class MarketplaceListingUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualizar listagem.

    O campo `packages` é opcional. Quando fornecido, substitui completamente
    os pacotes existentes do listing (delete + bulk_create).
    Os campos legados de dimensão foram removidos da atualização.
    """

    packages = ListingPackageSerializer(
        many=True,
        required=False,
        write_only=True,
        help_text=(
            'Lista de pacotes físicos. Quando fornecido, substitui todos os '
            'pacotes existentes do anúncio.'
        ),
    )

    class Meta:
        model = MarketplaceListing
        fields = [
            'title', 'price', 'quantity', 'description',
            'condition', 'is_active', 'shipping_address', 'packages',
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

    def validate_packages(self, value):
        """Se packages for fornecido, garante que não seja uma lista vazia."""
        if value is not None and len(value) == 0:
            raise serializers.ValidationError(
                'A lista de pacotes não pode ser vazia. '
                'Forneça pelo menos 1 pacote ou omita o campo para manter os pacotes atuais.'
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

    def update(self, instance, validated_data):
        """Substitui pacotes se fornecidos; caso contrário mantém os existentes."""
        packages_data = validated_data.pop('packages', None)
        instance = super().update(instance, validated_data)

        if packages_data is not None:
            # Substituição completa: remove os pacotes antigos e cria os novos
            instance.packages.all().delete()
            ListingPackage.objects.bulk_create([
                ListingPackage(listing=instance, **pkg) for pkg in packages_data
            ])

        return instance


class MarketplaceListingDetailSerializer(serializers.ModelSerializer):
    """Serializer detalhado de listagem"""
    product = ProductSerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    condition = ConditionSerializer(read_only=True)
    images = MarketplaceListingImageSerializer(many=True, read_only=True)
    packages = ListingPackageSerializer(many=True, read_only=True)
    seller_name = serializers.CharField(source='seller.get_full_name', read_only=True)
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    shipping_address = AddressSerializer(read_only=True)

    class Meta:
        model = MarketplaceListing
        fields = '__all__'