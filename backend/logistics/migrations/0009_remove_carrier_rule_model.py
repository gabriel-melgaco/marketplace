from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0008_add_melhorenvio_oauth_token'),
    ]

    operations = [
        migrations.DeleteModel(
            name='CarrierRule',
        ),
    ]
