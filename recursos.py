import json
from pathlib import Path

LIMITE_TEXTO_BOTON = 20
LIMITE_DESCRIPCION_ENLACE = 1024
TAMANO_MAXIMO_IMAGEN_BYTES = 5 * 1024 * 1024
EXTENSIONES_IMAGEN_PERMITIDAS = {".jpg", ".jpeg", ".png"}
FIRMAS_IMAGEN_PERMITIDAS = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
)

# Límites oficiales de Meta para mensajes interactivos (confirmados en
# developers.facebook.com/documentation/business-messaging/whatsapp/messages/
# interactive-reply-buttons-messages e interactive-list-messages, 3/11/2026).
LIMITE_BOTONES_POR_CONJUNTO = 3
LIMITE_ID_BOTON = 256
LIMITE_TITULO_BOTON_RESPUESTA = 20
LIMITE_CUERPO_INTERACTIVO = 1024
LIMITE_SECCIONES_LISTA = 10
LIMITE_FILAS_LISTA = 10
LIMITE_ID_FILA_LISTA = 200
LIMITE_TITULO_FILA_LISTA = 24
LIMITE_DESCRIPCION_FILA_LISTA = 72
LIMITE_TITULO_SECCION_LISTA = 24
LIMITE_TEXTO_BOTON_LISTA = 20

CLAVES_RAIZ_PERMITIDAS = {"ubicacion", "enlaces", "imagenes", "catalogo", "domicilio", "botones"}
CLAVE_PEDIDO_MINIMO = "pedido_minimo"


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
    if "imagenes" in datos:
        recursos["imagenes"] = _validar_imagenes(datos["imagenes"], ruta.name, ruta.parent)
    if "catalogo" in datos:
        recursos["catalogo"] = _validar_catalogo(datos["catalogo"], ruta.name)
    if "domicilio" in datos:
        recursos["domicilio"] = _validar_domicilio(datos["domicilio"], ruta.name)
    if "botones" in datos:
        recursos["botones"] = _validar_botones(datos["botones"], ruta.name)
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


def _validar_imagenes(imagenes, nombre_archivo: str, directorio_base: Path) -> dict:
    if not isinstance(imagenes, dict):
        raise ValueError(f"{nombre_archivo}: 'imagenes' debe ser un objeto.")

    resultado = {}
    for clave, imagen in imagenes.items():
        if not isinstance(imagen, dict):
            raise ValueError(f"{nombre_archivo}: 'imagenes.{clave}' debe ser un objeto.")

        descripcion = imagen.get("descripcion")
        if not isinstance(descripcion, str) or not (1 <= len(descripcion) <= LIMITE_DESCRIPCION_ENLACE):
            raise ValueError(
                f"{nombre_archivo}: 'imagenes.{clave}.descripcion' debe tener entre 1 y "
                f"{LIMITE_DESCRIPCION_ENLACE} caracteres."
            )

        archivo = imagen.get("archivo")
        if not isinstance(archivo, str) or not archivo.strip():
            raise ValueError(f"{nombre_archivo}: 'imagenes.{clave}.archivo' debe ser una ruta no vacía.")

        ruta_archivo = (directorio_base / archivo).resolve()
        if ruta_archivo.suffix.lower() not in EXTENSIONES_IMAGEN_PERMITIDAS:
            raise ValueError(
                f"{nombre_archivo}: 'imagenes.{clave}.archivo' debe ser .jpg, .jpeg o .png."
            )
        if not ruta_archivo.is_file():
            raise ValueError(f"{nombre_archivo}: 'imagenes.{clave}.archivo' no existe: {archivo}.")

        tamano = ruta_archivo.stat().st_size
        if tamano > TAMANO_MAXIMO_IMAGEN_BYTES:
            raise ValueError(
                f"{nombre_archivo}: 'imagenes.{clave}.archivo' pesa {tamano} bytes y supera "
                f"el máximo de {TAMANO_MAXIMO_IMAGEN_BYTES} bytes (5 MB) de WhatsApp."
            )

        with ruta_archivo.open("rb") as archivo_abierto:
            encabezado = archivo_abierto.read(8)
        if not any(encabezado.startswith(firma) for firma in FIRMAS_IMAGEN_PERMITIDAS):
            raise ValueError(
                f"{nombre_archivo}: 'imagenes.{clave}.archivo' no es un JPEG ni PNG válido."
            )

        resultado[clave] = {"clave": clave, "descripcion": descripcion, "archivo": ruta_archivo}

    return resultado


def _validar_catalogo(catalogo, nombre_archivo: str) -> dict:
    if not isinstance(catalogo, dict):
        raise ValueError(f"{nombre_archivo}: 'catalogo' debe ser un objeto.")

    # El menú se arma por código como una sola lista de WhatsApp a partir de todo
    # el catálogo (ver webhook.py): no puede tener más filas de las que WhatsApp
    # permite en una lista.
    if len(catalogo) > LIMITE_FILAS_LISTA:
        raise ValueError(
            f"{nombre_archivo}: 'catalogo' tiene {len(catalogo)} productos, más de los "
            f"{LIMITE_FILAS_LISTA} que WhatsApp permite en una sola lista (el menú se arma "
            "automáticamente a partir de todo el catálogo)."
        )

    resultado = {}
    for clave, producto in catalogo.items():
        if not isinstance(producto, dict):
            raise ValueError(f"{nombre_archivo}: 'catalogo.{clave}' debe ser un objeto.")

        if len(clave) > LIMITE_ID_FILA_LISTA or clave != clave.strip():
            raise ValueError(
                f"{nombre_archivo}: la clave 'catalogo.{clave}' se usa como id de fila de lista: debe "
                f"tener máximo {LIMITE_ID_FILA_LISTA} caracteres y sin espacios al inicio ni al final."
            )

        nombre = producto.get("nombre")
        if not isinstance(nombre, str) or not (1 <= len(nombre) <= LIMITE_TITULO_FILA_LISTA):
            raise ValueError(
                f"{nombre_archivo}: 'catalogo.{clave}.nombre' debe tener entre 1 y "
                f"{LIMITE_TITULO_FILA_LISTA} caracteres (se usa como título de fila en el menú "
                "de WhatsApp)."
            )

        precio = producto.get("precio")
        if isinstance(precio, bool) or not isinstance(precio, int) or precio <= 0:
            raise ValueError(
                f"{nombre_archivo}: 'catalogo.{clave}.precio' debe ser un número entero positivo, "
                "en pesos colombianos sin decimales."
            )

        unidad = producto.get("unidad")
        if not isinstance(unidad, str) or not unidad.strip():
            raise ValueError(f"{nombre_archivo}: 'catalogo.{clave}.unidad' debe ser un texto no vacío.")

        resultado[clave] = {"nombre": nombre, "precio": precio, "unidad": unidad}

    return resultado


def _validar_domicilio(domicilio, nombre_archivo: str) -> dict:
    if not isinstance(domicilio, dict):
        raise ValueError(f"{nombre_archivo}: 'domicilio' debe ser un objeto.")

    resultado = {}
    if CLAVE_PEDIDO_MINIMO in domicilio:
        pedido_minimo = domicilio[CLAVE_PEDIDO_MINIMO]
        if isinstance(pedido_minimo, bool) or not isinstance(pedido_minimo, int) or pedido_minimo < 0:
            raise ValueError(
                f"{nombre_archivo}: 'domicilio.{CLAVE_PEDIDO_MINIMO}' debe ser un número entero mayor o igual a 0."
            )
        resultado[CLAVE_PEDIDO_MINIMO] = pedido_minimo

    for clave, zona in domicilio.items():
        if clave == CLAVE_PEDIDO_MINIMO:
            continue
        if not isinstance(zona, dict):
            raise ValueError(f"{nombre_archivo}: 'domicilio.{clave}' debe ser un objeto.")

        costo = zona.get("costo")
        if isinstance(costo, bool) or not isinstance(costo, int) or costo < 0:
            raise ValueError(
                f"{nombre_archivo}: 'domicilio.{clave}.costo' debe ser un número entero mayor o igual a 0."
            )

        tiempo_estimado = zona.get("tiempo_estimado")
        if not isinstance(tiempo_estimado, str) or not tiempo_estimado.strip():
            raise ValueError(
                f"{nombre_archivo}: 'domicilio.{clave}.tiempo_estimado' debe ser un texto no vacío."
            )

        resultado[clave] = {"costo": costo, "tiempo_estimado": tiempo_estimado}

    return resultado


def _validar_botones(botones, nombre_archivo: str) -> dict:
    if not isinstance(botones, dict):
        raise ValueError(f"{nombre_archivo}: 'botones' debe ser un objeto.")

    resultado = {}
    for clave, conjunto in botones.items():
        if not isinstance(conjunto, dict):
            raise ValueError(f"{nombre_archivo}: 'botones.{clave}' debe ser un objeto.")

        descripcion = conjunto.get("descripcion")
        if not isinstance(descripcion, str) or not (1 <= len(descripcion) <= LIMITE_CUERPO_INTERACTIVO):
            raise ValueError(
                f"{nombre_archivo}: 'botones.{clave}.descripcion' debe tener entre 1 y "
                f"{LIMITE_CUERPO_INTERACTIVO} caracteres (límite de WhatsApp para el cuerpo de un "
                "mensaje con botones)."
            )

        opciones = conjunto.get("opciones")
        if not isinstance(opciones, list) or not (1 <= len(opciones) <= LIMITE_BOTONES_POR_CONJUNTO):
            raise ValueError(
                f"{nombre_archivo}: 'botones.{clave}.opciones' debe tener entre 1 y "
                f"{LIMITE_BOTONES_POR_CONJUNTO} elementos (límite de WhatsApp para botones de "
                "respuesta rápida)."
            )

        ids_vistos = set()
        opciones_validadas = []
        for indice, opcion in enumerate(opciones):
            if not isinstance(opcion, dict):
                raise ValueError(f"{nombre_archivo}: 'botones.{clave}.opciones[{indice}]' debe ser un objeto.")

            id_boton = opcion.get("id")
            if (
                not isinstance(id_boton, str)
                or not (1 <= len(id_boton) <= LIMITE_ID_BOTON)
                or id_boton != id_boton.strip()
            ):
                raise ValueError(
                    f"{nombre_archivo}: 'botones.{clave}.opciones[{indice}].id' debe ser un texto de 1 a "
                    f"{LIMITE_ID_BOTON} caracteres, sin espacios al inicio ni al final."
                )
            if id_boton in ids_vistos:
                raise ValueError(
                    f"{nombre_archivo}: 'botones.{clave}' tiene el id '{id_boton}' repetido; cada botón "
                    "del conjunto debe tener un id único."
                )
            ids_vistos.add(id_boton)

            titulo = opcion.get("titulo")
            if not isinstance(titulo, str) or not (1 <= len(titulo) <= LIMITE_TITULO_BOTON_RESPUESTA):
                raise ValueError(
                    f"{nombre_archivo}: 'botones.{clave}.opciones[{indice}].titulo' debe tener entre 1 y "
                    f"{LIMITE_TITULO_BOTON_RESPUESTA} caracteres (límite de WhatsApp para el título de "
                    "un botón)."
                )

            equivale_a = opcion.get("equivale_a")
            if not isinstance(equivale_a, str) or not equivale_a.strip():
                raise ValueError(
                    f"{nombre_archivo}: 'botones.{clave}.opciones[{indice}].equivale_a' debe ser un "
                    "texto no vacío: es el mensaje que se le pasa al asistente cuando el cliente toca "
                    "este botón."
                )

            opciones_validadas.append({"id": id_boton, "titulo": titulo, "equivale_a": equivale_a})

        resultado[clave] = {"descripcion": descripcion, "opciones": opciones_validadas}

    return resultado
