import os


def obtener_env(nombre: str, por_defecto: str | None = None) -> str | None:
    valor = os.getenv(nombre, por_defecto)
    if valor is None:
        return None
    return valor.strip()
