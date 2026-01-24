from minio import Minio
from django.conf import settings
from minio.error import S3Error



minio_client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


def get_minio_client():
    return minio_client

def delete_object(object_name: str):
    try:
        minio_client.remove_object(settings.MINIO_BUCKET, object_name)
    except S3Error as e:
        raise RuntimeError(f"Erro ao deletar objeto no MinIO: {e}")
