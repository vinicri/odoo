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
