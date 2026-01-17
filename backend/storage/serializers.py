from rest_framework import serializers


class PresignedUrlSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    content_type = serializers.CharField()


class PresignedUrlResponseSerializer(serializers.Serializer):
    upload_url = serializers.URLField()
    object_name = serializers.CharField()
    file_url = serializers.URLField()