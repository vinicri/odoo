import re
from odoo.exceptions import ValidationError


def is_valid_phone(phone):
    if not phone:
        return False
    phone_clean = "".join(filter(str.isdigit, phone))
    ddd = int(phone_clean[:2])
    if not (11 <= ddd <= 99):
        return False

    # Validar se não são números iguais
    if len(set(phone_clean)) == 1:
        return False

    if len(phone_clean) == 10:
        return True
    if len(phone_clean) == 11 and phone_clean[2] == "9":
        return True

    return False


def format_br_phone(phone):
    if not is_valid_phone(phone):
        raise ValidationError("Telefone inválido")
    if phone:
        val = re.sub("[^0-9]", "", phone)
        if len(val) == 10:
            return "%s %s-%s" % (val[0:2], val[2:6], val[6:10])
        elif len(val) == 11:
            return "%s %s-%s" % (val[0:2], val[2:7], val[7:11])
        else:
            return False


def format_number(value):
    return f"{value:0.2f}".replace(".", ",")
