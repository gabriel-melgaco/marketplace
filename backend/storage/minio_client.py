from minio import Minio
from django.conf import settings


minio_client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


def get_minio_client():
    return minio_client

def delete_object(bucket_name: str, object_name: str):
    minio_client.remove_object(bucket_name, object_name)
