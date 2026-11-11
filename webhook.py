import hashlib
import hmac
import logging
import re
import time
from pathlib import Path

from flask import Flask, Response, request

import pago_pedido
from almacenamiento import HistorialSQLite
from cerebro import Cerebro
from env import obtener_env
from flujo_pedido import ID_BOTON_HACER_PEDIDO, FlujoPedido
from llm import crear_proveedor_ia
from media_cache import obtener_media_id, reenviar_media_entrante
from mensajes_enriquecidos import (
    enviar_botones,
    enviar_cta_url,
    enviar_imagen,
    enviar_imagen_con_wamid,
    enviar_lista,
    enviar_plantilla,
    enviar_ubicacion,
)
from pedidos import Pedidos
from recursos import LIMITE_CUERPO_INTERACTIVO, cargar_recursos
from telefono import enmascarar_numero, normalizar_numero
from whatsapp import enviar_texto

logger = logging.getLogger(__name__)

# El servidor de desarrollo de Werkzeug registra la línea de petición completa,
# incluyendo la cadena de consulta (hub.verify_token, hub.challenge). Se sube su
# nivel para que esa línea no se registre; el logging propio (ver abajo) solo
# incluye método, ruta sin query string y código de estado.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

PUERTOS_PROHIBIDOS = {5000, 5001}

PERFIL_NEGOCIO_POR_DEFECTO = "panaderia"
PERFILES_NEGOCIO = {
    "panaderia": Path(__file__).parent / "negocio.md",
    "camilo": Path(__file__).parent / "perfil_camilo.md",
    "tamales": Path(__file__).parent / "perfil_tamales.md",
}
RECURSOS_NEGOCIO = {
    "panaderia": Path(__file__).parent / "recursos_panaderia.json",
    "camilo": Path(__file__).parent / "recursos_camilo.json",
    "tamales": Path(__file__).parent / "recursos_tamales.json",
}

# Perfiles de clientes reales (prospectos, demos privadas): sus archivos NUNCA
# viven en este repositorio ni en la imagen Docker — información de un
# tercero que todavía no es cliente. En vez de una lista blanca con el nombre
# de cada cliente (el repo es público), se resuelven por convención desde
# clientes/<clave>/, montada como volumen de solo lectura en docker-compose.yml
# (ver _ruta_perfil_cliente más abajo).
RAIZ_CLIENTES = Path(__file__).parent / "clientes"
PATRON_CLAVE_PERFIL_CLIENTE = re.compile(r"^[a-z0-9_]{1,40}$")

MENSAJE_DERIVACION_POR_DEFECTO = "Le comunico con una persona de nuestro equipo, que le responderá pronto."
MENSAJE_SOLO_TEXTO = (
    "Por ahora solo puedo atender mensajes de texto. "
    "Escríbeme tu pregunta y con gusto te ayudo."
)
MENSAJE_DUENO_RECORDATORIO = (
    "Este es el número del negocio. Aquí recibirá los avisos de pago para confirmar."
)

MARCADOR_MENSAJE_DERIVACION = "## Mensaje de derivación"
UMBRAL_MENSAJE_VIEJO_SEGUNDOS = 5 * 60

MENU_TITULO_SECCION = "Menú"
MENU_TEXTO_BOTON = "Ver menú"
# Cuerpos usados solo como respaldo: cuando el texto de la IA no cabe en el
# límite de WhatsApp para un mensaje interactivo, ese texto se envía aparte y
# el interactivo lleva este cuerpo corto fijo en su lugar.
MENU_TEXTO_CUERPO = "Este es nuestro menú:"
BOTONES_TEXTO_CUERPO_POR_DEFECTO = "Elija una opción:"


def _resolver_clave_perfil() -> str:
    clave = obtener_env("PERFIL_NEGOCIO") or PERFIL_NEGOCIO_POR_DEFECTO
    if clave in PERFILES_NEGOCIO or PATRON_CLAVE_PERFIL_CLIENTE.match(clave):
        return clave
    raise ValueError(
        "PERFIL_NEGOCIO no es válido. Debe ser uno de: "
        + ", ".join(sorted(PERFILES_NEGOCIO))
        + ", o la clave de un perfil de cliente (solo minúsculas, números y guion bajo, hasta "
        "40 caracteres) con su carpeta clientes/<clave>/ correspondiente."
    )


def _ruta_perfil_cliente(clave: str, nombre_archivo: str) -> Path:
    ruta = (RAIZ_CLIENTES / clave / nombre_archivo).resolve()
    if not ruta.is_relative_to(RAIZ_CLIENTES.resolve()):
        # Defensa en profundidad: con PATRON_CLAVE_PERFIL_CLIENTE esto no debería
        # ser alcanzable (la clave nunca puede traer "/" ni ".."), pero cubre
        # también el caso de un enlace simbólico dentro de clientes/ que apunte
        # fuera de esa carpeta.
        raise ValueError(f"Ruta de perfil de cliente fuera de {RAIZ_CLIENTES.name}/: '{clave}'.")
    if not ruta.is_file():
        raise ValueError(
            f"El perfil '{clave}' requiere clientes/{clave}/{nombre_archivo} "
            "(no incluido en este repositorio; pídeselo al desarrollador)."
        )
    return ruta


def _resolver_ruta_negocio() -> Path:
    clave = _resolver_clave_perfil()
    if clave in PERFILES_NEGOCIO:
        return PERFILES_NEGOCIO[clave]
    return _ruta_perfil_cliente(clave, f"perfil_{clave}.md")


def _resolver_ruta_recursos() -> Path:
    clave = _resolver_clave_perfil()
    if clave in RECURSOS_NEGOCIO:
        return RECURSOS_NEGOCIO[clave]
    return _ruta_perfil_cliente(clave, f"recursos_{clave}.json")


def _extraer_mensaje_derivacion(ruta_negocio: Path) -> str:
    contenido = ruta_negocio.read_text(encoding="utf-8")
    inicio = contenido.find(MARCADOR_MENSAJE_DERIVACION)
    if inicio == -1:
        return MENSAJE_DERIVACION_POR_DEFECTO

    resto = contenido[inicio + len(MARCADOR_MENSAJE_DERIVACION):]
    fin = resto.find("\n## ")
    seccion = resto if fin == -1 else resto[:fin]
    texto = seccion.strip()
    return texto or MENSAJE_DERIVACION_POR_DEFECTO


def _es_inicio_de_pedido(mensaje: dict, recursos: dict) -> bool:
    # Un pedido empieza cuando el cliente elige un producto de la lista del
    # menú, o toca el botón "Hacer pedido" de la bienvenida — en ambos casos
    # desde FUERA del modo pedido (si ya hay uno en construcción, el mensaje
    # nunca llega hasta aquí: se enruta directo a FlujoPedido).
    if mensaje.get("type") != "interactive":
        return False
    interactivo = mensaje.get("interactive", {})
    tipo = interactivo.get("type")
    if tipo == "button_reply":
        return interactivo.get("button_reply", {}).get("id") == ID_BOTON_HACER_PEDIDO
    if tipo == "list_reply":
        return interactivo.get("list_reply", {}).get("id") in recursos.get("catalogo", {})
    return False


def _firma_valida(cuerpo_crudo: bytes, firma_recibida: str | None) -> bool:
    app_secret = obtener_env("META_APP_SECRET")
    if not app_secret or not firma_recibida or not firma_recibida.startswith("sha256="):
        return False
    firma_esperada = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), cuerpo_crudo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida)


def crear_app(
    cerebro: Cerebro | None = None,
    historial_dedup: HistorialSQLite | None = None,
    enviar_texto_fn=enviar_texto,
    enviar_ubicacion_fn=enviar_ubicacion,
    enviar_cta_url_fn=enviar_cta_url,
    enviar_imagen_fn=enviar_imagen,
    enviar_botones_fn=enviar_botones,
    enviar_lista_fn=enviar_lista,
    obtener_media_id_fn=obtener_media_id,
    reenviar_media_fn=reenviar_media_entrante,
    enviar_plantilla_fn=enviar_plantilla,
    enviar_imagen_con_wamid_fn=enviar_imagen_con_wamid,
    recursos: dict | None = None,
    pedidos: Pedidos | None = None,
    perfil: str | None = None,
    mensaje_derivacion: str | None = None,
    numero_dueno: str | None = None,
    plantilla_aviso_dueno_nombre: str | None = None,
    plantilla_aviso_dueno_idioma: str | None = None,
    reloj=time.time,
) -> Flask:
    app = Flask(__name__)

    if historial_dedup is None:
        historial_dedup = HistorialSQLite()
    if pedidos is None:
        pedidos = Pedidos()
    if perfil is None:
        perfil = _resolver_clave_perfil()
    if numero_dueno is None:
        valor_numero_dueno = obtener_env("NUMERO_DUENO")
        numero_dueno = normalizar_numero(valor_numero_dueno) if valor_numero_dueno else None
    numero_dueno = numero_dueno or None
    if plantilla_aviso_dueno_nombre is None:
        plantilla_aviso_dueno_nombre = obtener_env("PLANTILLA_AVISO_DUENO_NOMBRE") or None
    if plantilla_aviso_dueno_idioma is None:
        plantilla_aviso_dueno_idioma = obtener_env("PLANTILLA_AVISO_DUENO_IDIOMA") or None
    if bool(plantilla_aviso_dueno_nombre) != bool(plantilla_aviso_dueno_idioma):
        # Solo una de las dos configurada: se trata como "no configurada" (cae
        # al aviso libre de siempre) en vez de romper el arranque por esto.
        logger.warning(
            "PLANTILLA_AVISO_DUENO_NOMBRE y PLANTILLA_AVISO_DUENO_IDIOMA deben configurarse "
            "juntas; con solo una de las dos, el aviso al dueño usa el mensaje libre de siempre."
        )
        plantilla_aviso_dueno_nombre = None
        plantilla_aviso_dueno_idioma = None
    if cerebro is None or mensaje_derivacion is None:
        ruta_negocio_resuelta = _resolver_ruta_negocio()
    if cerebro is None:
        ruta_recursos_resuelta = _resolver_ruta_recursos()
        cerebro = Cerebro(
            crear_proveedor_ia(),
            historial_dedup,
            ruta_negocio=ruta_negocio_resuelta,
            ruta_recursos=ruta_recursos_resuelta,
        )
        if recursos is None:
            recursos = cargar_recursos(ruta_recursos_resuelta)
    if recursos is None:
        recursos = {}
    if mensaje_derivacion is None:
        mensaje_derivacion = _extraer_mensaje_derivacion(ruta_negocio_resuelta)

    flujo_pedido = FlujoPedido(
        pedidos=pedidos,
        catalogo=recursos.get("catalogo", {}),
        domicilio=recursos.get("domicilio", {}),
        mensaje_derivacion=mensaje_derivacion,
        enviar_texto_fn=enviar_texto_fn,
        enviar_botones_fn=enviar_botones_fn,
        enviar_lista_fn=enviar_lista_fn,
        reloj=reloj,
        numero_dueno=numero_dueno,
        enviar_imagen_fn=enviar_imagen_fn,
        obtener_media_id_fn=obtener_media_id_fn,
        reenviar_media_fn=reenviar_media_fn,
        imagen_qr=recursos.get("imagenes", {}).get("qr_ejemplo"),
        enviar_plantilla_fn=enviar_plantilla_fn,
        enviar_imagen_con_wamid_fn=enviar_imagen_con_wamid_fn,
        plantilla_aviso_dueno_nombre=plantilla_aviso_dueno_nombre,
        plantilla_aviso_dueno_idioma=plantilla_aviso_dueno_idioma,
    )

    @app.after_request
    def _registrar_peticion(respuesta):
        # request.path nunca incluye la cadena de consulta (hub.verify_token,
        # hub.challenge quedan fuera), a diferencia del log por defecto de Werkzeug.
        # /salud no se registra: lo golpea el healthcheck de Docker cada 30
        # segundos y no aporta nada para depurar un problema real. Esta es la
        # única línea por petición (el accesslog propio de gunicorn está
        # desactivado en gunicorn.conf.py para no duplicarla).
        if request.path != "/salud":
            logger.info("%s %s -> %s", request.method, request.path, respuesta.status_code)
        return respuesta

    def _procesar_mensaje(mensaje: dict) -> None:
        id_mensaje = mensaje.get("id")
        numero_remitente = mensaje.get("from", "")
        numero_enmascarado = enmascarar_numero(numero_remitente)

        timestamp_mensaje = mensaje.get("timestamp")
        if timestamp_mensaje is not None:
            try:
                antiguedad_segundos = reloj() - int(timestamp_mensaje)
            except (TypeError, ValueError):
                antiguedad_segundos = None
            if antiguedad_segundos is not None and antiguedad_segundos > UMBRAL_MENSAJE_VIEJO_SEGUNDOS:
                logger.info(
                    "Mensaje antiguo ignorado (tipo=%s, antiguedad_segundos=%d)",
                    mensaje.get("type"),
                    int(antiguedad_segundos),
                )
                return

        if id_mensaje and not historial_dedup.marcar_si_nuevo(id_mensaje):
            logger.info("Mensaje duplicado ignorado (remitente=%s)", numero_enmascarado)
            return

        if numero_dueno and numero_remitente == numero_dueno:
            logger.info("Mensaje del dueño recibido.")
            _procesar_respuesta_dueno(mensaje)
            return

        pedido_activo = pedidos.obtener_activo(numero_remitente)
        if pedido_activo is not None:
            logger.info("Mensaje atendido por el flujo de pedido (remitente=%s)", numero_enmascarado)
            flujo_pedido.manejar_mensaje(numero_remitente, mensaje)
            return
        if _es_inicio_de_pedido(mensaje, recursos):
            logger.info("Pedido en construcción iniciado (remitente=%s)", numero_enmascarado)
            flujo_pedido.iniciar(numero_remitente, perfil, mensaje)
            return

        tipo_mensaje = mensaje.get("type")
        if tipo_mensaje == "text":
            texto = mensaje.get("text", {}).get("body", "")
        elif tipo_mensaje == "interactive":
            texto = _resolver_texto_interactivo(mensaje.get("interactive", {}))
            if texto is None:
                logger.info(
                    "Respuesta interactiva con id desconocido o no reconocida, ignorada "
                    "(remitente=%s)",
                    numero_enmascarado,
                )
                return
        else:
            logger.info(
                "Mensaje no-texto recibido (remitente=%s, tipo=%s)",
                numero_enmascarado,
                tipo_mensaje,
            )
            enviar_texto_fn(numero_remitente, MENSAJE_SOLO_TEXTO)
            return

        respuesta = cerebro.responder(numero_remitente, texto)

        if respuesta.derivar:
            logger.info("Conversación derivada a una persona (remitente=%s)", numero_enmascarado)
            enviar_texto_fn(numero_remitente, mensaje_derivacion)
            if respuesta.adjuntos:
                # Al derivar, el texto que se envía es el mensaje fijo de derivación,
                # no el de la IA: enviar un adjunto sin ese contexto sería confuso o
                # contradictorio (p. ej. una foto sin ninguna frase que la anuncie).
                logger.info(
                    "%d adjunto(s) descartado(s) por derivación (remitente=%s)",
                    len(respuesta.adjuntos),
                    numero_enmascarado,
                )
        else:
            # Un adjunto de botones o menú trae su propio mensaje interactivo con
            # cuerpo: si se enviara el texto de la IA por separado Y ese cuerpo,
            # el cliente vería dos mensajes seguidos para lo mismo (ver bug de la
            # prueba en vivo de la sub-fase 2). Por eso el primero de esos
            # adjuntos absorbe el texto de la IA como su propio cuerpo, y solo el
            # resto de adjuntos (ubicación, enlaces, imágenes, u otro botones/menú
            # adicional) se envían como mensajes aparte, igual que antes.
            adjunto_interactivo = next(
                (a for a in respuesta.adjuntos if a["tipo"] in ("botones", "menu")), None
            )
            if adjunto_interactivo is not None:
                _enviar_interactivo_con_texto(numero_remitente, respuesta.texto, adjunto_interactivo)
            else:
                enviar_texto_fn(numero_remitente, respuesta.texto)

            for adjunto in respuesta.adjuntos:
                if adjunto is adjunto_interactivo:
                    continue
                _enviar_adjunto(numero_remitente, adjunto)

    def _procesar_estado(estado: dict) -> None:
        # sent/delivered/read nunca generan ninguna línea de log, a propósito.
        # Solo "failed" (Meta aceptó el mensaje pero no lo entregó) se registra,
        # nunca el contenido de ningún mensaje.
        if estado.get("status") != "failed":
            return

        wamid = estado.get("id")
        numero_enmascarado = enmascarar_numero(estado.get("recipient_id", ""))
        errores = estado.get("errors") or []
        codigo = errores[0].get("code") if errores else None
        titulo = errores[0].get("title") if errores else None
        info = pedidos.info_aviso_dueno_por_wamid(wamid) if wamid else None

        if info is not None and info["tipo"] == "comprobante":
            # Caso esperado si la ventana de 24 horas está cerrada: el aviso
            # principal ya se garantizó por plantilla, así que esto es solo
            # informativo, nunca una advertencia, y nunca "pedido desconocido".
            logger.info(
                "El comprobante del pedido #%s no se entregó aparte; el aviso principal al "
                "dueño fue por plantilla.",
                info["pedido_id"],
            )
            return

        pedido_id = info["pedido_id"] if info is not None else "desconocido"
        logger.warning(
            "Mensaje no entregado (status=failed, codigo=%s, titulo=%s, destino=%s, pedido=%s)",
            codigo, titulo, numero_enmascarado, pedido_id,
        )

    def _id_pedido_desde_boton(id_boton: str, prefijo: str) -> int | None:
        try:
            return int(id_boton[len(prefijo):])
        except ValueError:
            return None

    def _id_boton_entrante(mensaje: dict) -> str | None:
        # Un botón de respuesta rápida en un mensaje libre llega como
        # interactive.button_reply.id; el mismo tipo de botón en una PLANTILLA
        # (ver docs/plantilla_aviso_dueno.md) llega distinto: type == "button",
        # con el payload en mensaje["button"]["payload"]. Se aceptan los dos
        # formatos con exactamente las mismas validaciones.
        if mensaje.get("type") == "interactive":
            return mensaje.get("interactive", {}).get("button_reply", {}).get("id")
        if mensaje.get("type") == "button":
            return mensaje.get("button", {}).get("payload")
        return None

    def _procesar_respuesta_dueno(mensaje: dict) -> None:
        # Mensajes del dueño NUNCA llegan a cerebro.responder ni a flujo_pedido:
        # solo se reconocen los botones de pago [Pago recibido]/[No ha llegado];
        # cualquier otra cosa (un "hola" para abrir la ventana de 24 horas, un
        # botón desconocido) recibe un texto fijo recordándole qué es este número.
        ahora = reloj()
        id_boton = _id_boton_entrante(mensaje)
        if id_boton is not None:
            if id_boton.startswith(pago_pedido.PREFIJO_BOTON_PAGO_RECIBIDO):
                pedido_id = _id_pedido_desde_boton(id_boton, pago_pedido.PREFIJO_BOTON_PAGO_RECIBIDO)
                if pedido_id is not None:
                    resultado = pago_pedido.confirmar_pago(pedidos, pedido_id, ahora, enviar_texto_fn)
                    enviar_texto_fn(numero_dueno, resultado)
                    return
            elif id_boton.startswith(pago_pedido.PREFIJO_BOTON_PAGO_NO_LLEGO):
                pedido_id = _id_pedido_desde_boton(id_boton, pago_pedido.PREFIJO_BOTON_PAGO_NO_LLEGO)
                if pedido_id is not None:
                    resultado = pago_pedido.rechazar_pago(pedidos, pedido_id, ahora, enviar_texto_fn)
                    enviar_texto_fn(numero_dueno, resultado)
                    return

        enviar_texto_fn(numero_dueno, MENSAJE_DUENO_RECORDATORIO)

    def _enviar_interactivo_con_texto(numero: str, texto: str, adjunto: dict) -> None:
        tipo = adjunto["tipo"]
        datos = adjunto["datos"]
        if len(texto) <= LIMITE_CUERPO_INTERACTIVO:
            cuerpo = texto
        else:
            enviar_texto_fn(numero, texto)
            cuerpo = BOTONES_TEXTO_CUERPO_POR_DEFECTO if tipo == "botones" else MENU_TEXTO_CUERPO

        if tipo == "botones":
            opciones = [{"id": opcion["id"], "titulo": opcion["titulo"]} for opcion in datos["opciones"]]
            enviar_botones_fn(numero, cuerpo, opciones)
        elif tipo == "menu":
            _enviar_menu(numero, datos, cuerpo)

    def _enviar_adjunto(numero: str, adjunto: dict) -> None:
        # cerebro.py ya validó el adjunto contra los recursos del perfil: aquí solo
        # se despacha al tipo correspondiente, en el orden en que llegaron.
        tipo = adjunto["tipo"]
        datos = adjunto["datos"]
        if tipo == "ubicacion":
            enviar_ubicacion_fn(numero, datos["latitud"], datos["longitud"], datos["nombre"], datos["direccion"])
        elif tipo == "enlace":
            enviar_cta_url_fn(numero, datos["descripcion"], datos["texto_boton"], datos["url"])
        elif tipo == "imagen":
            media_id = obtener_media_id_fn(datos["clave"], datos["archivo"])
            if media_id is not None:
                enviar_imagen_fn(numero, media_id, caption=datos["descripcion"])
        elif tipo == "botones":
            opciones = [{"id": opcion["id"], "titulo": opcion["titulo"]} for opcion in datos["opciones"]]
            enviar_botones_fn(numero, datos["descripcion"], opciones)
        elif tipo == "menu":
            _enviar_menu(numero, datos)

    def _enviar_menu(numero: str, catalogo: dict, cuerpo: str = MENU_TEXTO_CUERPO) -> None:
        # El menú SIEMPRE se arma aquí, a partir del catálogo validado del perfil:
        # la IA nunca decide los productos, nombres ni precios que aparecen.
        filas = [
            {
                "id": clave,
                "titulo": producto["nombre"],
                "descripcion": f"${producto['precio']:,}".replace(",", "."),
            }
            for clave, producto in catalogo.items()
        ]
        secciones = [{"titulo": MENU_TITULO_SECCION, "filas": filas}]
        enviar_lista_fn(numero, cuerpo, MENU_TEXTO_BOTON, secciones)

    def _resolver_texto_interactivo(interactivo: dict) -> str | None:
        # Nunca se le pasa a la IA el id ni el título tal cual llegan de WhatsApp:
        # solo un texto equivalente ya validado contra la lista blanca de botones
        # del perfil. La única lista que existe hoy es el menú (armado desde el
        # catálogo), y elegir una fila de ahí siempre inicia un pedido antes de
        # llegar a esta función (ver _es_inicio_de_pedido) — por eso no hay una
        # rama "list_reply" aquí: quedaría inalcanzable.
        if interactivo.get("type") == "button_reply":
            id_recibido = interactivo.get("button_reply", {}).get("id")
            for conjunto in recursos.get("botones", {}).values():
                for opcion in conjunto["opciones"]:
                    if opcion["id"] == id_recibido:
                        return opcion["equivale_a"]
            return None
        return None

    @app.route("/salud", methods=["GET"])
    def salud():
        return Response("ok", status=200, mimetype="text/plain")

    @app.route("/webhook", methods=["GET"])
    def verificar_webhook():
        modo = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if modo == "subscribe" and token == obtener_env("WHATSAPP_VERIFY_TOKEN"):
            return Response(challenge or "", status=200, mimetype="text/plain")
        return Response("Token de verificación inválido", status=403, mimetype="text/plain")

    @app.route("/webhook", methods=["POST"])
    def recibir_webhook():
        firma_recibida = request.headers.get("X-Hub-Signature-256")
        if not _firma_valida(request.get_data(), firma_recibida):
            if not firma_recibida:
                logger.warning("Firma de webhook ausente.")
            else:
                # Nunca se registra la firma recibida ni el secreto: solo el hecho
                # de que no coincidieron.
                logger.warning("Firma de webhook presente pero no coincide.")
            return Response("Firma inválida", status=403, mimetype="text/plain")

        datos = request.get_json(silent=True) or {}

        for entrada in datos.get("entry", []):
            for cambio in entrada.get("changes", []):
                valor = cambio.get("value", {})

                if "statuses" in valor:
                    for estado in valor.get("statuses", []):
                        try:
                            _procesar_estado(estado)
                        except Exception:
                            logger.exception("Error inesperado al procesar un status entrante.")
                    # Una notificación de estado nunca trae "messages" en el mismo
                    # value (son mutuamente excluyentes); no requiere respuesta.
                    continue

                for mensaje in valor.get("messages", []):
                    try:
                        _procesar_mensaje(mensaje)
                    except Exception:
                        # Un mensaje con error no debe impedir responder 200 a Meta
                        # ni bloquear el procesamiento de los demás mensajes del lote.
                        logger.exception("Error inesperado al procesar un mensaje entrante.")

        return Response("OK", status=200, mimetype="text/plain")

    return app


if __name__ == "__main__":
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    load_dotenv()

    valor_puerto = obtener_env("PUERTO", "8000")
    try:
        puerto = int(valor_puerto)
    except ValueError:
        raise ValueError("PUERTO no es válido. Debe ser un número entero.") from None

    if puerto in PUERTOS_PROHIBIDOS:
        raise ValueError(
            "El puerto 5000/5001 está reservado en este equipo. Usa otro valor en PUERTO."
        )

    crear_app().run(host="0.0.0.0", port=puerto, debug=False)
