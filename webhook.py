import hashlib
import hmac
import logging
import time
from pathlib import Path

from flask import Flask, Response, request

from almacenamiento import HistorialSQLite
from cerebro import Cerebro
from env import obtener_env
from llm import crear_proveedor_ia
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
}

MENSAJE_DERIVACION_POR_DEFECTO = "Le comunico con una persona de nuestro equipo, que le responderá pronto."
MENSAJE_SOLO_TEXTO = (
    "Por ahora solo puedo atender mensajes de texto. "
    "Escríbeme tu pregunta y con gusto te ayudo."
)

MARCADOR_MENSAJE_DERIVACION = "## Mensaje de derivación"
UMBRAL_MENSAJE_VIEJO_SEGUNDOS = 5 * 60


def _enmascarar_numero(numero: str) -> str:
    if not numero:
        return "desconocido"
    if len(numero) <= 4:
        return "*" * len(numero)
    return "*" * (len(numero) - 4) + numero[-4:]


def _resolver_ruta_negocio() -> Path:
    clave = obtener_env("PERFIL_NEGOCIO") or PERFIL_NEGOCIO_POR_DEFECTO
    if clave not in PERFILES_NEGOCIO:
        raise ValueError(
            "PERFIL_NEGOCIO no es válido. Valores permitidos: "
            + ", ".join(sorted(PERFILES_NEGOCIO))
            + "."
        )
    return PERFILES_NEGOCIO[clave]


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
    mensaje_derivacion: str | None = None,
    reloj=time.time,
) -> Flask:
    app = Flask(__name__)

    if historial_dedup is None:
        historial_dedup = HistorialSQLite()
    if cerebro is None or mensaje_derivacion is None:
        ruta_negocio_resuelta = _resolver_ruta_negocio()
    if cerebro is None:
        cerebro = Cerebro(crear_proveedor_ia(), historial_dedup, ruta_negocio=ruta_negocio_resuelta)
    if mensaje_derivacion is None:
        mensaje_derivacion = _extraer_mensaje_derivacion(ruta_negocio_resuelta)

    @app.after_request
    def _registrar_peticion(respuesta):
        # request.path nunca incluye la cadena de consulta (hub.verify_token,
        # hub.challenge quedan fuera), a diferencia del log por defecto de Werkzeug.
        logger.info("%s %s -> %s", request.method, request.path, respuesta.status_code)
        return respuesta

    def _procesar_mensaje(mensaje: dict) -> None:
        id_mensaje = mensaje.get("id")
        numero_remitente = mensaje.get("from", "")
        numero_enmascarado = _enmascarar_numero(numero_remitente)

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

        if mensaje.get("type") != "text":
            logger.info(
                "Mensaje no-texto recibido (remitente=%s, tipo=%s)",
                numero_enmascarado,
                mensaje.get("type"),
            )
            enviar_texto_fn(numero_remitente, MENSAJE_SOLO_TEXTO)
            return

        texto = mensaje.get("text", {}).get("body", "")
        respuesta = cerebro.responder(numero_remitente, texto)

        if respuesta.derivar:
            logger.info("Conversación derivada a una persona (remitente=%s)", numero_enmascarado)
            enviar_texto_fn(numero_remitente, mensaje_derivacion)
        else:
            enviar_texto_fn(numero_remitente, respuesta.texto)

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
                    # Notificación de estado (enviado/entregado/leído): no requiere respuesta.
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
