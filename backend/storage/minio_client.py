import json
import logging

from minio import Minio
from django.conf import settings
from minio.error import S3Error

logger = logging.getLogger(__name__)

_minio_client = None


def get_minio_client():
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=getattr(settings, 'MINIO_USE_SSL', False),
        )
    return _minio_client


def delete_object(object_name: str):
    try:
        get_minio_client().remove_object(settings.MINIO_BUCKET, object_name)
    except S3Error as e:
        raise RuntimeError(f"Erro ao deletar objeto no MinIO: {e}")


def ensure_bucket_ready():
    """
    Garante que o bucket existe, tem policy de leitura pública
    e CORS configurado para upload via browser.
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET

    # Criar bucket se não existe
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Bucket '%s' criado.", bucket)

    # Policy de leitura pública (para servir imagens via URL direta)
    public_read_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/products/*"],
            }
        ],
    })

    try:
        existing_policy = client.get_bucket_policy(bucket)
    except S3Error:
        existing_policy = None

    if not existing_policy:
        client.set_bucket_policy(bucket, public_read_policy)
        logger.info("Policy de leitura pública aplicada ao bucket '%s'.", bucket)
