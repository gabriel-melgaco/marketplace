import re
from rest_framework import serializers
from .models import CustomUser

# ======================================================
# Helpers
# ======================================================

def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def is_valid_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def calc_digit(digits):
        s = sum(int(d) * w for d, w in zip(digits, range(len(digits) + 1, 1, -1)))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    d1 = calc_digit(cpf[:9])
    d2 = calc_digit(cpf[:10])
    return cpf[-2:] == f"{d1}{d2}"


def is_valid_cnpj(cnpj: str) -> bool:
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def calc_digit(digits, weights):
        s = sum(int(d) * w for d, w in zip(digits, weights))
        r = s % 11
        return 0 if r < 2 else 11 - r

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1

    d1 = calc_digit(cnpj[:12], w1)
    d2 = calc_digit(cnpj[:13], w2)
    return cnpj[-2:] == f"{d1}{d2}"


# ======================================================
# Mixins de validação
# ======================================================

class CpfCnpjValidationMixin:
    """
    Valida CPF/CNPJ:
    - formato
    - dígitos verificadores
    - unicidade
    - suporta create e update
    """

    def validate_cpf(self, value):
        if not value:
            return value

        value = only_digits(value)

        qs = CustomUser.objects.filter(cpf=value)

        # evita conflito ao atualizar o próprio usuário
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError("CPF já cadastrado.")

        if len(value) == 11:
            if not is_valid_cpf(value):
                raise serializers.ValidationError("CPF inválido.")
            return value

        if len(value) == 14:
            if not is_valid_cnpj(value):
                raise serializers.ValidationError("CNPJ inválido.")
            return value

        raise serializers.ValidationError(
            "Informe CPF ou CNPJ válido, apenas números."
        )


class FullNameValidationMixin:
    """
    Valida nome completo
    """

    def validate_full_name(self, value):
        if len(value.split()) < 2 or len(value.strip()) < 8:
            raise serializers.ValidationError(
                "Deverá ser inserido o nome completo."
            )
        return value
