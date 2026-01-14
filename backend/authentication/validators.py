import re

def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def validate_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def calc_digit(digits):
        s = sum(int(d) * w for d, w in zip(digits, range(len(digits) + 1, 1, -1)))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    d1 = calc_digit(cpf[:9])
    d2 = calc_digit(cpf[:10])

    return cpf[-2:] == f"{d1}{d2}"


def validate_cnpj(cnpj: str) -> bool:
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