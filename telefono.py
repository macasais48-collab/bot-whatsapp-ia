def enmascarar_numero(numero: str) -> str:
    if not numero:
        return "desconocido"
    if len(numero) <= 4:
        return "*" * len(numero)
    return "*" * (len(numero) - 4) + numero[-4:]
