from django.db import models
from authentication.models import CustomUser


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['name']
    
    def __str__(self):
        if self.parent:
            return f'{self.name} > {self.parent.name}'
        return self.name


class Series(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = 'Série'
        verbose_name_plural = 'Séries'

    def __str__(self):
        return self.name


class Products(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    code = models.CharField(max_length=100, null=True, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products'
    )

    series = models.ForeignKey(
        Series,
        on_delete=models.PROTECT,
        related_name='products'
    )

    image_url = models.URLField(max_length=500, blank=True, default='')

    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'


    def __str__(self):
        return self.name
    

class Condition(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = 'Condição'
        verbose_name_plural = 'Condições'

    def __str__(self):
        return self.name
    

class Brand(models.Model):
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(unique=True)

    logo = models.CharField(max_length=255, blank=True, null=True)

    website = models.URLField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'
        ordering = ['name']

    def __str__(self):
        return self.name


class MarketplaceListing(models.Model):
    product = models.ForeignKey(
        Products,
        on_delete=models.CASCADE,
        related_name='listing'
    )
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='listing'
    )
    title = models.CharField(
        max_length=150,
        help_text="Título do anúncio"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name='listing'
    )
    quantity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    description = models.TextField(max_length=255)
    condition = models.ForeignKey(
        Condition,
        on_delete=models.PROTECT,
        related_name='listing'
    )
    views_count = models.PositiveIntegerField(default=0)

    weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Peso em kg (legado — use packages)"
    )
    height_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Altura em cm (legado — use packages)"
    )
    width_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Largura em cm (legado — use packages)"
    )
    length_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Comprimento em cm (legado — use packages)"
    )

    shipping_address = models.ForeignKey(
        'logistics.Address',
        on_delete=models.PROTECT,
        related_name='listings',
        null=True,
        blank=True,
        help_text="Endereço de envio do anúncio"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Listagem de Produto'
        verbose_name_plural = 'Listagem de Produtos'

    def __str__(self):
        return self.title


class MarketplaceListingImages(models.Model):
    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name='images'
    )

    image_url = models.URLField(max_length=500)

    object_name = models.CharField(max_length=255)
   
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Imagem do Produto'
        verbose_name_plural = 'Imagens dos Produtos'

    def __str__(self):
        return f'Imagem - {self.listing.product.name}'


class ListingPackage(models.Model):
    """
    Representa um pacote físico de um anúncio (MarketplaceListing).

    Um anúncio pode ter múltiplos pacotes — por exemplo, um equipamento de
    academia que vem desmontado em duas caixas de tamanhos diferentes.

    Cada pacote gera um volume separado no payload do Melhor Envio, permitindo
    cálculo de frete mais preciso e eliminando a necessidade de consolidação
    manual de dimensões.

    Migração de legado: Listings criados antes desta feature têm as dimensões
    nos campos weight_kg / height_cm / width_cm / length_cm do próprio listing.
    O serviço ME faz fallback para esses campos quando não há pacotes.
    """

    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name='packages'
    )
    weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Peso do pacote em kg"
    )
    height_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Altura do pacote em cm"
    )
    width_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Largura do pacote em cm"
    )
    length_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Comprimento do pacote em cm"
    )
    description = models.CharField(
        max_length=100,
        blank=True,
        help_text="Descrição opcional do pacote (ex: 'Caixa grande')"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pacote do Anúncio'
        verbose_name_plural = 'Pacotes do Anúncio'
        ordering = ['id']

    def __str__(self):
        return f'Pacote {self.id} - {self.listing.title} ({self.weight_kg}kg)'