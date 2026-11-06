LONGITUD_MINIMA_NUMERO = 10
LONGITUD_MAXIMA_NUMERO = 15


def enmascarar_numero(numero: str) -> str:
    if not numero:
        return "desconocido"
    if len(numero) <= 4:
        return "*" * len(numero)
    return "*" * (len(numero) - 4) + numero[-4:]


def normalizar_numero(numero: str) -> str:
    # Se queda solo con los dígitos: quita "+", espacios y guiones, para que
    # distintas formas de escribir el mismo número (+57 300 111 2233,
    # 57-300-111-2233, 573001112233) coincidan con el formato del remitente
    # que envía WhatsApp (solo dígitos, sin "+").
    return "".join(caracter for caracter in numero if caracter.isdigit())


def numero_parece_valido(numero: str) -> bool:
    return numero.isdigit() and LONGITUD_MINIMA_NUMERO <= len(numero) <= LONGITUD_MAXIMA_NUMERO
