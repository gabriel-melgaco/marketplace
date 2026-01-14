from auth_kit.serializers.registration import RegisterSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .validators import only_digits, validate_cnpj, validate_cpf
from .models import CustomUser

User = get_user_model()

class CustomRegisterSerializer(RegisterSerializer):
    full_name = serializers.CharField()
    cpf = serializers.CharField()
    birthday = serializers.DateField()
    picture = serializers.CharField()
    first_name = None
    last_name = None

    def validate_full_name(self, value):
        if len(value.split()) < 2 or len(value.strip()) < 8:
            raise serializers.ValidationError('Deverá ser inserido o nome completo')
        return value
    
    def validate_cpf(self, value):
        value = only_digits(value)

        if CustomUser.objects.filter(cpf=value).exists():
            raise serializers.ValidationError('CPF já cadastrado.')

        elif len(value) == 11:
            if not validate_cpf(value):
                raise serializers.ValidationError("CPF inválido.")
            return value

        elif len(value) == 14:
            if not validate_cnpj(value):
                raise serializers.ValidationError("CNPJ inválido.")
            return value

        raise serializers.ValidationError(
            "Informe CPF ou CNPJ válido, apenas números."
        )
        

    def save(self, **kwargs):
        user = super().save()

        user.full_name = self.validated_data["full_name"]
        user.cpf = self.validated_data["cpf"]
        user.birthday = self.validated_data["birthday"]
        user.picture = self.validated_data["picture"]

        user.save()
        return user
    

class CustomUserSerializer(serializers.ModelSerializer):
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
