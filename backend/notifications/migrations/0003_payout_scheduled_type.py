# Generated manually on 2026-03-21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_listing_created_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreference',
            name='payout_scheduled_email',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='notificationpreference',
            name='payout_scheduled_ws',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('order_created', 'Pedido Criado'),
                    ('order_status_changed', 'Status do Pedido Alterado'),
                    ('payment_confirmed', 'Pagamento Confirmado'),
                    ('payment_failed', 'Falha no Pagamento'),
                    ('dispute_opened', 'Disputa Aberta'),
                    ('shipment_created', 'Envio Criado'),
                    ('shipment_status_updated', 'Status do Envio Atualizado'),
                    ('delivery_scheduled', 'Entrega Agendada'),
                    ('delivery_confirmed', 'Entrega Confirmada'),
                    ('new_message', 'Nova Mensagem'),
                    ('seller_verified', 'Vendedor Verificado'),
                    ('listing_blocked', 'Anúncio Bloqueado'),
                    ('listing_created', 'Anúncio Publicado'),
                    ('payout_scheduled', 'Repasse Agendado'),
                ],
                max_length=50,
            ),
        ),
    ]
