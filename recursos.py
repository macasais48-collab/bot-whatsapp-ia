import json
from pathlib import Path

LIMITE_TEXTO_BOTON = 20
LIMITE_DESCRIPCION_ENLACE = 1024

CLAVES_RAIZ_PERMITIDAS = {"ubicacion", "enlaces"}


def cargar_recursos(ruta: Path) -> dict:
    contenido = ruta.read_text(encoding="utf-8")
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as error:
        raise ValueError(f"{ruta.name} no es un JSON válido: {error}") from None

    if not isinstance(datos, dict):
        raise ValueError(f"{ruta.name} debe contener un objeto JSON en la raíz.")

    claves_desconocidas = set(datos) - CLAVES_RAIZ_PERMITIDAS
    if claves_desconocidas:
        raise ValueError(
            f"{ruta.name} tiene claves no reconocidas: {', '.join(sorted(claves_desconocidas))}."
        )

    recursos = {}
    if "ubicacion" in datos:
        recursos["ubicacion"] = _validar_ubicacion(datos["ubicacion"], ruta.name)
    if "enlaces" in datos:
        recursos["enlaces"] = _validar_enlaces(datos["enlaces"], ruta.name)
    return recursos


def _validar_ubicacion(ubicacion, nombre_archivo: str) -> dict:
    if not isinstance(ubicacion, dict):
        raise ValueError(f"{nombre_archivo}: 'ubicacion' debe ser un objeto.")

    for campo in ("nombre", "direccion"):
        valor = ubicacion.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"{nombre_archivo}: 'ubicacion.{campo}' debe ser un texto no vacío.")

    try:
        latitud = float(ubicacion.get("latitud"))
        longitud = float(ubicacion.get("longitud"))
    except (TypeError, ValueError):
        raise ValueError(
            f"{nombre_archivo}: 'ubicacion.latitud' y 'ubicacion.longitud' deben ser números."
        ) from None

    if not -90 <= latitud <= 90:
        raise ValueError(f"{nombre_archivo}: 'ubicacion.latitud' fuera de rango (-90 a 90).")
    if not -180 <= longitud <= 180:
        raise ValueError(f"{nombre_archivo}: 'ubicacion.longitud' fuera de rango (-180 a 180).")

    return {
        "latitud": latitud,
        "longitud": longitud,
        "nombre": ubicacion["nombre"],
        "direccion": ubicacion["direccion"],
    }


def _validar_enlaces(enlaces, nombre_archivo: str) -> dict:
    if not isinstance(enlaces, dict):
        raise ValueError(f"{nombre_archivo}: 'enlaces' debe ser un objeto.")

    resultado = {}
    for clave, enlace in enlaces.items():
        if not isinstance(enlace, dict):
            raise ValueError(f"{nombre_archivo}: 'enlaces.{clave}' debe ser un objeto.")

        url = enlace.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"{nombre_archivo}: 'enlaces.{clave}.url' debe ser una URL https.")

        texto_boton = enlace.get("texto_boton")
        if not isinstance(texto_boton, str) or not (1 <= len(texto_boton) <= LIMITE_TEXTO_BOTON):
            raise ValueError(
                f"{nombre_archivo}: 'enlaces.{clave}.texto_boton' debe tener entre 1 y "
                f"{LIMITE_TEXTO_BOTON} caracteres (límite de WhatsApp para botones)."
            )

        descripcion = enlace.get("descripcion")
        if not isinstance(descripcion, str) or not (1 <= len(descripcion) <= LIMITE_DESCRIPCION_ENLACE):
            raise ValueError(
                f"{nombre_archivo}: 'enlaces.{clave}.descripcion' debe tener entre 1 y "
                f"{LIMITE_DESCRIPCION_ENLACE} caracteres."
            )

        resultado[clave] = {"url": url, "texto_boton": texto_boton, "descripcion": descripcion}

    return resultado
