# Generated manually - adds product_amount, shipping_amount, shipping_status to PaymentSplit

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_sellerconnectedaccountproxy'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentsplit',
            name='product_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Subtotal somente dos produtos (base da comissão)',
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name='paymentsplit',
            name='shipping_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Frete retido pela plataforma para cobrir débitos ME',
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name='paymentsplit',
            name='shipping_status',
            field=models.CharField(
                choices=[
                    ('held', 'Retido'),
                    ('released', 'Liberado p/ Logística'),
                    ('refunded', 'Reembolsado'),
                ],
                default='held',
                help_text='Status do frete retido: held/released/refunded',
                max_length=20,
            ),
        ),
    ]
