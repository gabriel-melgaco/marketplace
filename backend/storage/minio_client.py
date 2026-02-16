import json
import logging
from minio import Minio
from minio.error import S3Error
from django.conf import settings

logger = logging.getLogger(__name__)

_internal_client = None
_public_client = None


def get_internal_minio_client():
    global _internal_client
    if _internal_client is None:
        _internal_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
    return _internal_client


def get_public_minio_client():
    global _public_client
    if _public_client is None:
        _public_client = Minio(
            settings.MINIO_PUBLIC_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=True,
        )
    return _public_client


def delete_object(object_name: str):
    try:
        get_internal_minio_client().remove_object(
            settings.MINIO_BUCKET,
            object_name,
        )
    except S3Error as e:
        raise RuntimeError(f"Erro ao deletar objeto no MinIO: {e}")


def ensure_bucket_ready():
    client = get_internal_minio_client()
    bucket = settings.MINIO_BUCKET

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Bucket '%s' criado.", bucket)

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
        client.get_bucket_policy(bucket)
    except S3Error:
        client.set_bucket_policy(bucket, public_read_policy)
        logger.info("Policy pública aplicada ao bucket '%s'.", bucket)
