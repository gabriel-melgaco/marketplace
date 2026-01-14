from auth_kit.serializers.registration import RegisterSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import CustomUser
from .validators import CpfCnpjValidationMixin, FullNameValidationMixin

User = get_user_model()

class CustomRegisterSerializer(CpfCnpjValidationMixin, FullNameValidationMixin, RegisterSerializer):
    full_name = serializers.CharField()
    cpf = serializers.CharField()
    birthday = serializers.DateField()
    picture = serializers.CharField()
    first_name = None
    last_name = None

    def save(self, **kwargs):
        user = super().save()

        user.full_name = self.validated_data["full_name"]
        user.cpf = self.validated_data["cpf"]
        user.birthday = self.validated_data["birthday"]
        user.picture = self.validated_data["picture"]

        user.save()
        return user


class CustomUserSerializer(CpfCnpjValidationMixin, FullNameValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "birthday",
            "cpf",
            "picture",
            "is_active",
        )


#Serializers only for documentation
class LoginUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    birthday = serializers.DateField()
    cpf = serializers.CharField()
    picture = serializers.CharField()
    is_active = serializers.BooleanField()


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(allow_blank=True)
    access_expiration = serializers.DateTimeField()
    refresh_expiration = serializers.DateTimeField()
    user = LoginUserResponseSerializer()
