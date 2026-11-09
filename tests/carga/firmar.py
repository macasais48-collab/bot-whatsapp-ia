"""Firma HMAC para los payloads de la prueba de carga — misma fórmula que
webhook._firma_valida, pero siempre con un secreto de prueba, nunca el real."""
import hashlib
import hmac


def firmar(cuerpo: bytes, secreto: str) -> str:
    return "sha256=" + hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
