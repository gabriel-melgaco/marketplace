from django.core.management.base import BaseCommand
from storage.minio_client import ensure_bucket_ready


class Command(BaseCommand):
    help = "Configura bucket MinIO: cria bucket, aplica policy de leitura publica."

    def handle(self, *args, **options):
        ensure_bucket_ready()
        self.stdout.write(self.style.SUCCESS("MinIO bucket configurado com sucesso."))
