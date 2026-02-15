from django.db import models
from orders.models import Order, OrderItem
from authentication.models import CustomUser
from django.core.exceptions import ValidationError


class DeliveryMethod(models.TextChoices):
    """Tipos de método de entrega"""
    SHIPPING = 'shipping', 'Envio via Transportadora'
    IN_PERSON = 'in_person', 'Retirada Presencial'


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
        ('created', 'Etiqueta Criada'),
        ('pending', 'Pendente'),
        ('released', 'Etiqueta Paga'),
        ('generated', 'Etiqueta Gerada'),
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


class OrderDelivery(models.Model):
    """
    Registro de opção de entrega escolhida para um pedido.
    Cada pedido pode ter múltiplas entregas (uma por vendedor).
    """

    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('confirmed', 'Confirmado'),
        ('ready', 'Pronto para Retirada/Envio'),
        ('in_transit', 'Em Trânsito'),
        ('delivered', 'Entregue/Retirado'),
        ('cancelled', 'Cancelado'),
        ('failed', 'Falhou'),
    ]

    # Relacionamentos
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='deliveries'
    )

    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='order_deliveries'
    )

    # Tipo de entrega escolhida
    delivery_method = models.CharField(
        max_length=20,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.SHIPPING
    )

    # Status da entrega
    status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='pending'
    )

    # Informações específicas para cada tipo
    # Para SHIPPING: referência ao Shipment
    shipment = models.OneToOneField(
        'Shipment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_delivery'
    )

    # Para IN_PERSON: referência ao InPersonDelivery
    in_person_delivery = models.OneToOneField(
        'InPersonDelivery',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_delivery'
    )

    # Custo de entrega (0 para presencial)
    delivery_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Entrega do Pedido'
        verbose_name_plural = 'Entregas do Pedido'
        ordering = ['-created_at']
        unique_together = ['order', 'seller']
        indexes = [
            models.Index(fields=['order', 'seller']),
            models.Index(fields=['delivery_method', 'status']),
        ]

    def __str__(self):
        return f'{self.get_delivery_method_display()} - {self.order.order_number} - {self.seller.email}'

    def clean(self):
        """Valida que apenas um tipo de entrega está preenchido"""
        if self.delivery_method == DeliveryMethod.SHIPPING and not self.shipment:
            if self.status not in ['pending', 'cancelled']:
                raise ValidationError('Envio via transportadora requer um Shipment associado')

        if self.delivery_method == DeliveryMethod.IN_PERSON and not self.in_person_delivery:
            if self.status not in ['pending', 'cancelled']:
                raise ValidationError('Entrega presencial requer um InPersonDelivery associado')

    def get_delivery_info(self):
        """Retorna informações consolidadas da entrega"""
        if self.delivery_method == DeliveryMethod.SHIPPING and self.shipment:
            return {
                'type': 'shipping',
                'carrier': self.shipment.carrier_name,
                'service': self.shipment.carrier_service,
                'tracking_code': self.shipment.melhorenvio_tracking_code,
                'tracking_url': self.shipment.tracking_url,
                'estimated_delivery': self.shipment.estimated_delivery_date,
                'cost': float(self.delivery_cost)
            }
        elif self.delivery_method == DeliveryMethod.IN_PERSON and self.in_person_delivery:
            return {
                'type': 'in_person',
                'location_name': self.in_person_delivery.meeting_location_name,
                'address': self.in_person_delivery.meeting_address,
                'scheduled_date': self.in_person_delivery.scheduled_date,
                'scheduled_time': self.in_person_delivery.scheduled_time,
                'contact_phone': self.in_person_delivery.seller_contact_phone,
                'cost': 0
            }
        return {}


class InPersonDelivery(models.Model):
    """
    Detalhes de uma entrega presencial (retirada com o vendedor).
    Armazena local, data/hora do encontro e informações de contato.
    """

    MEETING_STATUS_CHOICES = [
        ('pending_schedule', 'Aguardando Agendamento'),
        ('scheduled', 'Agendado'),
        ('confirmed', 'Confirmado por Ambas as Partes'),
        ('in_progress', 'Em Andamento'),
        ('completed', 'Concluído'),
        ('cancelled', 'Cancelado'),
        ('no_show', 'Não Compareceu'),
    ]

    # Relacionamento com Order (através de OrderDelivery)
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='in_person_deliveries_as_seller'
    )

    buyer = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='in_person_deliveries_as_buyer'
    )

    # Status do encontro
    meeting_status = models.CharField(
        max_length=20,
        choices=MEETING_STATUS_CHOICES,
        default='pending_schedule'
    )

    # Local do encontro
    meeting_location_name = models.CharField(
        max_length=200,
        help_text='Nome do local (ex: Shopping X, Estação Y)'
    )

    meeting_address = models.JSONField(
        help_text='Endereço completo do local de encontro'
    )

    meeting_notes = models.TextField(
        blank=True,
        help_text='Observações sobre o local (ex: próximo à entrada principal)'
    )

    # Data e hora do encontro
    scheduled_date = models.DateField(
        null=True,
        blank=True,
        help_text='Data agendada para o encontro'
    )

    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        help_text='Horário agendado para o encontro'
    )

    # Informações de contato
    seller_contact_phone = models.CharField(
        max_length=20,
        help_text='Telefone do vendedor para contato'
    )

    buyer_contact_phone = models.CharField(
        max_length=20,
        help_text='Telefone do comprador para contato'
    )

    # Confirmações
    seller_confirmed = models.BooleanField(default=False)
    buyer_confirmed = models.BooleanField(default=False)
    seller_confirmed_at = models.DateTimeField(null=True, blank=True)
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Confirmações de conclusão (ambas as partes devem confirmar)
    seller_completed = models.BooleanField(default=False)
    buyer_completed = models.BooleanField(default=False)
    seller_completed_at = models.DateTimeField(null=True, blank=True)
    buyer_completed_at = models.DateTimeField(null=True, blank=True)

    completion_notes = models.TextField(
        blank=True,
        help_text='Observações sobre a conclusão da entrega'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Entrega Presencial'
        verbose_name_plural = 'Entregas Presenciais'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'buyer']),
            models.Index(fields=['meeting_status']),
            models.Index(fields=['scheduled_date', 'scheduled_time']),
        ]

    def __str__(self):
        return f'Encontro {self.seller.email} - {self.buyer.email} em {self.meeting_location_name}'

    def is_fully_confirmed(self):
        """Verifica se ambas as partes confirmaram o encontro"""
        return self.seller_confirmed and self.buyer_confirmed

    def is_fully_completed(self):
        """Verifica se ambas as partes confirmaram a conclusão"""
        return self.seller_completed and self.buyer_completed

    def can_be_completed(self):
        """Verifica se a entrega pode ser marcada como concluída"""
        return self.meeting_status in ['pending_schedule', 'scheduled', 'confirmed', 'in_progress']

    def save(self, *args, **kwargs):
        if self.is_fully_confirmed() and self.meeting_status in ('pending_schedule', 'scheduled'):
            self.meeting_status = 'confirmed'

        if self.is_fully_completed() and self.meeting_status in ('pending_schedule', 'scheduled', 'confirmed', 'in_progress'):
            self.meeting_status = 'completed'
            if not self.completed_at:
                from django.utils import timezone
                self.completed_at = timezone.now()

        super().save(*args, **kwargs)


class DeliveryStatusLog(models.Model):
    """Histórico de mudanças de status de entregas"""

    order_delivery = models.ForeignKey(
        OrderDelivery,
        on_delete=models.CASCADE,
        related_name='status_logs'
    )

    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)

    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de Status de Entrega'
        verbose_name_plural = 'Logs de Status de Entrega'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_delivery} - {self.from_status} → {self.to_status}'


class CarrierRule(models.Model):
    """
    Regras de dimensões e peso por transportadora/modalidade.

    Armazena as restrições de cada transportadora para validar pacotes
    ANTES de chamar a API do Melhor Envio ou filtrar resultados retornados.

    Cada registro representa uma modalidade de uma transportadora.
    Ex: Correios SEDEX/PAC, Correios Mini Envios, Jadlog Pegaki, etc.
    """

    # Identificação da transportadora e modalidade
    carrier_name = models.CharField(
        max_length=100,
        help_text='Nome da transportadora como retornado pelo Melhor Envio (ex: Correios, Jadlog)'
    )
    modality = models.CharField(
        max_length=200,
        help_text='Nome da modalidade/serviço (ex: SEDEX/PAC, Mini Envios, Jadlog Pegaki)'
    )

    # Dimensões mínimas (cm) - nullable para transportadoras sem mínimo
    min_height = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Altura mínima em cm'
    )
    min_width = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Largura mínima em cm'
    )
    min_length = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Comprimento mínimo em cm'
    )

    # Dimensões máximas (cm)
    max_height = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Altura máxima em cm'
    )
    max_width = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Largura máxima em cm'
    )
    max_length = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Comprimento máximo em cm'
    )

    # Peso (kg)
    min_weight = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        help_text='Peso mínimo em kg'
    )
    max_weight = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Peso máximo em kg'
    )

    # Soma das dimensões (cm) - algumas transportadoras limitam L+A+C
    min_sum_dimensions = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Soma mínima das dimensões (L+A+C) em cm'
    )
    max_sum_dimensions = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Soma máxima das dimensões (L+A+C) em cm'
    )

    # Maior lado individual (cm) - J&T Express limita o maior lado a 120cm
    max_single_side = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Tamanho máximo de qualquer lado individual em cm'
    )

    # Limite para taxa de não mecanizável (cm)
    non_mechanizable_threshold = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Limite em cm acima do qual incide taxa de não mecanizável (ex: 70cm para Correios)'
    )

    # Controle
    is_active = models.BooleanField(
        default=True,
        help_text='Se a regra está ativa. Regras inativas são ignoradas na validação.'
    )
    notes = models.TextField(
        blank=True,
        help_text='Observações sobre a regra (ex: taxa extra para >70cm)'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Regra de Transportadora'
        verbose_name_plural = 'Regras de Transportadoras'
        ordering = ['carrier_name', 'modality']
        unique_together = ['carrier_name', 'modality']
        indexes = [
            models.Index(fields=['carrier_name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        status = 'ativa' if self.is_active else 'inativa'
        return f'{self.carrier_name} - {self.modality} ({status})'