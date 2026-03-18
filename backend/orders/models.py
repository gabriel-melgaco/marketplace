from django.db import models
from django.core.validators import MinValueValidator
from authentication.models import CustomUser
from products.models import MarketplaceListing
import uuid
from django.utils import timezone


class Order(models.Model):
    """Modelo principal de pedido"""
    
    STATUS_CHOICES = [
        ('pending_payment', 'Aguardando Pagamento'),
        ('paid', 'Pagamento Confirmado'),
        ('processing', 'Aguardando Envio'),
        ('shipped', 'Enviado'),
        ('delivered', 'Entregue'),
        ('cancelled', 'Cancelado'),
        ('failed', 'Falha no Pagamento'),
        ('refunded', 'Reembolsado'),
    ]
    
    # Identificação
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    
    # Relacionamentos
    buyer = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='orders'
    )

    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='seller_orders',
        null=True,
        blank=True,
        help_text='Vendedor deste pedido. Todos os itens pertencem a este único vendedor.'
    )

    # Status e valores
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Endereço de entrega (snapshot do endereço no momento da compra)
    shipping_address = models.JSONField()
    
    # NOVO: Serviços de frete escolhidos por vendedor
    # Formato: {"seller_id": {"service_id": 1, "service_name": "PAC", "cost": 17.90}}
    shipping_services = models.JSONField(default=dict, blank=True)
    
    # Método de pagamento
    payment_method = models.CharField(max_length=20, blank=True)
    
    # Observações
    buyer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['order_number']),
        ]
    
    def __str__(self):
        return f'Pedido #{self.order_number}'
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            # Gera número do pedido (ex: ORD-2026-00001)
            year = timezone.now().year
            last_order = Order.objects.filter(
                order_number__startswith=f'ORD-{year}'
            ).order_by('-order_number').first()
            
            if last_order:
                last_num = int(last_order.order_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.order_number = f'ORD-{year}-{new_num:05d}'
        
        super().save(*args, **kwargs)
    
    def get_sellers(self):
        """Retorna lista de vendedores deste pedido"""
        return CustomUser.objects.filter(
            sales__order=self
        ).distinct()


class OrderItem(models.Model):
    """Itens do pedido"""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='sales'
    )
    
    # Snapshot dos dados no momento da compra
    product_name = models.CharField(max_length=200)
    product_code = models.CharField(max_length=100, blank=True)
    brand_name = models.CharField(max_length=150)
    condition_name = models.CharField(max_length=100)
    
    # Valores
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Frete individual (cada vendedor pode ter frete diferente)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Dimensões (para cálculo de frete)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2)
    width_cm = models.DecimalField(max_digits=6, decimal_places=2)
    length_cm = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Endereço de origem do vendedor (snapshot)
    seller_address = models.JSONField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Item do Pedido'
        verbose_name_plural = 'Itens do Pedido'
        indexes = [
            models.Index(fields=['order', 'seller']),
        ]
    
    def __str__(self):
        return f'{self.product_name} - Pedido #{self.order.order_number}'
    
    def save(self, *args, **kwargs):
        # Calcula subtotal automaticamente
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """Histórico de mudanças de status do pedido"""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Histórico de Status'
        verbose_name_plural = 'Históricos de Status'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.order.order_number}: {self.old_status} → {self.new_status}'


class Cart(models.Model):
    """Carrinho de compras do usuário"""
    
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Carrinho'
        verbose_name_plural = 'Carrinhos'
    
    def __str__(self):
        return f'Carrinho de {self.user.email}'
    
    def get_total(self):
        """Calcula total do carrinho (apenas produtos, sem frete)"""
        return sum(item.get_subtotal() for item in self.items.all())
    
    def get_sellers(self):
        """Retorna lista de vendedores dos itens no carrinho"""
        # CORRIGIDO: usar o relacionamento correto através de listing
        return CustomUser.objects.filter(
            listing__cart_items__cart=self
        ).distinct()


class CartItem(models.Model):
    """Itens no carrinho"""
    
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Item do Carrinho'
        verbose_name_plural = 'Itens do Carrinho'
        unique_together = ['cart', 'listing']
    
    def __str__(self):
        return f'{self.listing.product.name} ({self.quantity}x)'
    
    def get_subtotal(self):
        """Calcula subtotal do item"""
        return self.listing.price * self.quantity