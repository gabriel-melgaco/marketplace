from rest_framework import serializers
from .models import (
    Category, Series, Products, Brand, 
    Condition, MarketplaceListing, MarketplaceListingImages
)
from logistics.models import Address
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
        """
        Valida peso do produto
        
        Limites da API Melhor Envio:
        - Mínimo: 0.3kg (300g)
        - Máximo: 30kg
        """
        if value < 0.3:
            raise serializers.ValidationError(
                "Peso mínimo permitido é 0.3kg (300 gramas). "
                "Este é o limite mínimo das transportadoras."
            )
        if value > 30:
            raise serializers.ValidationError(
                "Peso máximo permitido é 30kg. "
                "Para produtos mais pesados, entre em contato com o suporte ou trate diretamente com o vendedor através do chat."
            )
        return value
    
    def validate_height_cm(self, value):
        """
        Valida altura do produto
        
        Limites da API Melhor Envio:
        - Mínimo: 2cm
        - Máximo: 100cm
        """
        if value < 2:
            raise serializers.ValidationError(
                "Altura mínima permitida é 2cm. "
                "Este é o limite mínimo das transportadoras."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Altura máxima permitida é 100cm (1 metro). "
                "Para produtos maiores, entre em contato com o suporte."
            )
        return value
    
    def validate_width_cm(self, value):
        """
        Valida largura do produto
        
        Limites da API Melhor Envio:
        - Mínimo: 11cm
        - Máximo: 100cm
        """
        if value < 11:
            raise serializers.ValidationError(
                "Largura mínima permitida é 11cm. "
                "Este é o limite mínimo das transportadoras."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Largura máxima permitida é 100cm (1 metro). "
                "Para produtos maiores, entre em contato com o suporte."
            )
        return value
    
    def validate_length_cm(self, value):
        """
        Valida comprimento do produto
        
        Limites da API Melhor Envio:
        - Mínimo: 16cm
        - Máximo: 100cm
        """
        if value < 16:
            raise serializers.ValidationError(
                "Comprimento mínimo permitido é 16cm. "
                "Este é o limite mínimo das transportadoras."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Comprimento máximo permitido é 100cm (1 metro). "
                "Para produtos maiores, entre em contato com o suporte."
            )
        return value
    
    def validate(self, data):
        request = self.context.get('request')

        # Segurança extra (boas práticas)
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                'Usuário não autenticado.'
            )

        user = request.user

        # ===============================
        # Validação de usuário com cpf
        # ===============================
        cpf = getattr(user, 'cpf', None)

        if not cpf:
            raise serializers.ValidationError(
                'Você precisa cadastrar um CPF válido antes de criar produtos.'
            )

        # ===============================
        # Validação soma das dimensões
        # ===============================
        height = data.get('height_cm', 0)
        width = data.get('width_cm', 0)
        length = data.get('length_cm', 0)

        total_dimensions = height + width + length

        if total_dimensions > 200:
            raise serializers.ValidationError({
                'non_field_errors': [
                    f'A soma das dimensões é {total_dimensions}cm. '
                    'O máximo permitido pelos Correios é 200cm.'
                ]
            })

        # ===============================
        # Validação endereço de envio
        # ===============================
        has_shipping_address = Address.objects.filter(
            user=user,
            is_shipping_address=True,
            is_active=True
        ).exists()

        if not has_shipping_address:
            raise serializers.ValidationError(
                'Você precisa cadastrar um endereço de envio antes de criar produtos.'
            )

        return data
    
    def create(self, validated_data):
        # O seller será adicionado na view
        return super().create(validated_data)


class MarketplaceListingUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar listagem"""
    class Meta:
        model = MarketplaceListing
        fields = [
            'price', 'quantity', 'description', 
            'condition', 'weight_kg', 'height_cm', 
            'width_cm', 'length_cm', 'is_active'
        ]
    
    # Mesmas validações do create
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
        if value < 0.3:
            raise serializers.ValidationError(
                "Peso mínimo permitido é 0.3kg (300 gramas)."
            )
        if value > 30:
            raise serializers.ValidationError(
                "Peso máximo permitido é 30kg."
            )
        return value
    
    def validate_height_cm(self, value):
        if value < 2:
            raise serializers.ValidationError(
                "Altura mínima permitida é 2cm."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Altura máxima permitida é 100cm."
            )
        return value
    
    def validate_width_cm(self, value):
        if value < 11:
            raise serializers.ValidationError(
                "Largura mínima permitida é 11cm."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Largura máxima permitida é 100cm."
            )
        return value
    
    def validate_length_cm(self, value):
        if value < 16:
            raise serializers.ValidationError(
                "Comprimento mínimo permitido é 16cm."
            )
        if value > 100:
            raise serializers.ValidationError(
                "Comprimento máximo permitido é 100cm."
            )
        return value
    
    def validate(self, data):
        """Validação da soma das dimensões"""
        # Pegar valores atuais se não foram fornecidos
        instance = self.instance
        
        height = data.get('height_cm', instance.height_cm if instance else 0)
        width = data.get('width_cm', instance.width_cm if instance else 0)
        length = data.get('length_cm', instance.length_cm if instance else 0)
        
        total_dimensions = height + width + length
        
        if total_dimensions > 200:
            raise serializers.ValidationError({
                'non_field_errors': [
                    f'A soma das dimensões é {total_dimensions}cm, '
                    f'mas o máximo permitido é 200cm.'
                ]
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
    
    class Meta:
        model = MarketplaceListing
        fields = '__all__'