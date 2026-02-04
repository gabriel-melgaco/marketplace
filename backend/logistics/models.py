from django.db import models
from orders.models import Order, OrderItem
from authentication.models import CustomUser


class ShippingQuote(models.Model):
    """Cotação de frete do Melhor Envio"""
    
    # Relacionamento temporário (antes de criar o pedido)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='shipping_quotes'
    )
    
    # Agrupamento por vendedor
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='shipping_quotes_as_seller',
        null=True,
        blank=True
    )
    
    # Endereços
    origin_zipcode = models.CharField(max_length=9)
    origin_address = models.JSONField()
    destination_zipcode = models.CharField(max_length=9)
    destination_address = models.JSONField()
    
    # Dimensões do pacote
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    height = models.DecimalField(max_digits=6, decimal_places=2)
    width = models.DecimalField(max_digits=6, decimal_places=2)
    length = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Valor declarado para seguro
    declared_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Cotações retornadas pelo Melhor Envio (por vendedor)
    quotes_data = models.JSONField()  # Armazena todas as opções de frete
    
    # Metadados
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # Cotações expiram em 24h
    
    class Meta:
        verbose_name = 'Cotação de Frete'
        verbose_name_plural = 'Cotações de Frete'
        ordering = ['-created_at']
    
    def __str__(self):
        if self.seller:
            return f'Cotação Vendedor {self.seller.email} - {self.destination_zipcode}'
        return f'Cotação {self.user.email} - {self.destination_zipcode}'


class Shipment(models.Model):
    """Envio criado no Melhor Envio - Um envio por vendedor"""
    
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('posted', 'Postado'),
        ('in_transit', 'Em Trânsito'),
        ('out_for_delivery', 'Saiu para Entrega'),
        ('delivered', 'Entregue'),
        ('cancelled', 'Cancelado'),
        ('returned', 'Devolvido'),
    ]
    
    # Relacionamentos
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='shipments'
    )
    
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='shipments'
    )
    
    # IDs do Melhor Envio
    melhorenvio_order_id = models.CharField(max_length=255, unique=True)
    melhorenvio_tracking_code = models.CharField(max_length=255, blank=True)
    
    # Informações da transportadora
    carrier_name = models.CharField(max_length=100)
    carrier_service = models.CharField(max_length=100)
    
    # Valores
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2)
    insurance_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status e rastreamento
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    tracking_url = models.URLField(blank=True)
    
    # Dimensões e peso do pacote
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    height = models.DecimalField(max_digits=6, decimal_places=2)
    width = models.DecimalField(max_digits=6, decimal_places=2)
    length = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Endereços
    origin_address = models.JSONField()
    destination_address = models.JSONField()
    
    # Etiqueta
    label_url = models.URLField(blank=True)
    label_generated_at = models.DateTimeField(null=True, blank=True)
    
    # Previsão de entrega
    estimated_delivery_date = models.DateField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Envio'
        verbose_name_plural = 'Envios'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Envio {self.melhorenvio_tracking_code} - {self.order.order_number}'


class ShipmentTracking(models.Model):
    """Histórico de rastreamento do envio"""
    
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='tracking_history'
    )
    
    status = models.CharField(max_length=100)
    description = models.TextField()
    location = models.CharField(max_length=255, blank=True)
    
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Rastreamento'
        verbose_name_plural = 'Rastreamentos'
        ordering = ['-occurred_at']
    
    def __str__(self):
        return f'{self.shipment.melhorenvio_tracking_code} - {self.status}'


class Address(models.Model):
    """Endereços salvos do usuário"""
    
    ADDRESS_TYPE_CHOICES = [
        ('home', 'Residencial'),
        ('work', 'Comercial'),
        ('shipping', 'Envio (Vendedor)'),
        ('other', 'Outro'),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    
    # Tipo e apelido
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE_CHOICES, default='home')
    nickname = models.CharField(max_length=50, blank=True)  # Ex: "Casa", "Trabalho", "Depósito"
    
    # Flag para endereço de envio (vendedores)
    is_shipping_address = models.BooleanField(default=False)
    
    # Dados do destinatário
    recipient_name = models.CharField(max_length=200)
    recipient_phone = models.CharField(max_length=20)
    
    # Endereço
    zipcode = models.CharField(max_length=9)
    street = models.CharField(max_length=200)
    number = models.CharField(max_length=20)
    complement = models.CharField(max_length=100, blank=True)
    neighborhood = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)  # Sigla do estado
    country = models.CharField(max_length=2, default='BR')
    
    # Flags
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Endereço'
        verbose_name_plural = 'Endereços'
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f'{self.nickname or self.address_type} - {self.user.email}'
    
    def save(self, *args, **kwargs):
        # Se este endereço for marcado como padrão, remove o padrão dos outros
        if self.is_default:
            Address.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        
        # Se for endereço de envio, marca o tipo automaticamente
        if self.is_shipping_address:
            self.address_type = 'shipping'
        
        super().save(*args, **kwargs)
    
    def to_dict(self):
        """Converte endereço para formato JSON"""
        return {
            'recipient_name': self.recipient_name,
            'recipient_phone': self.recipient_phone,
            'zipcode': self.zipcode,
            'street': self.street,
            'number': self.number,
            'complement': self.complement,
            'neighborhood': self.neighborhood,
            'city': self.city,
            'state': self.state,
            'country': self.country,
        }