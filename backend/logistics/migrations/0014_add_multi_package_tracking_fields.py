# Generated manually on 2026-02-28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0013_alter_shipment_status'),
    ]

    operations = [
        # 1. Adiciona melhorenvio_tracking_codes em Shipment
        migrations.AddField(
            model_name='shipment',
            name='melhorenvio_tracking_codes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de tracking codes ME (um por pacote físico). melhorenvio_tracking_code mantém o primeiro para retrocompatibilidade.',
            ),
        ),
        # 2. Adiciona package_me_id em ShipmentTracking
        migrations.AddField(
            model_name='shipmenttracking',
            name='package_me_id',
            field=models.CharField(
                blank=True,
                default='',
                help_text='ID ME do carrinho ao qual este evento pertence (identifica o pacote).',
                max_length=255,
            ),
            preserve_default=False,
        ),
        # 3. Substitui a unicidade anterior (shipment, occurred_at) por
        #    (shipment, occurred_at, package_me_id) para que dois pacotes do mesmo
        #    shipment possam ter eventos no mesmo instante sem violar constraints.
        migrations.AlterUniqueTogether(
            name='shipmenttracking',
            unique_together={('shipment', 'occurred_at', 'package_me_id')},
        ),
    ]
