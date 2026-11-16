"""Aviso al negocio cuando el bot deriva una conversación a una persona
(sub-fase 6a).

Antes, al derivar, el cliente recibía el mensaje fijo de derivación y nadie del
negocio se enteraba: con la Cloud API el número del bot no se puede abrir en la
app de WhatsApp. Ahora el dueño (NUMERO_DUENO) recibe el teléfono del cliente y
un resumen breve de la solicitud, redactado por la IA.

- El teléfono del cliente va COMPLETO en el contenido del aviso (misma
  excepción deliberada que el aviso de pedido nuevo: el negocio necesita
  contactarlo). En el log, siempre enmascarado. El resumen nunca se registra.
- Por plantilla si está configurada (llega fuera de la ventana de 24 horas);
  si no, texto libre. En ambos casos se guarda el wamid para asociar un
  status "failed" (ver webhook._procesar_estado).
- Antirrepetición: como máximo un aviso por cliente cada 30 minutos.
"""
import logging

from pedido_resumen import una_linea
from pedidos import Pedidos
from telefono import enmascarar_numero

logger = logging.getLogger(__name__)

LIMITE_RESUMEN = 300
VENTANA_ANTIRREPETICION_SEGUNDOS = 30 * 60
RESUMEN_NO_DISPONIBLE = "Sin resumen disponible; contacte al cliente para saber qué necesita."


def resumen_para_aviso(resumen: str | None) -> str:
    """Una sola línea apta para variable de plantilla (sin saltos de línea,
    tabulaciones ni 4+ espacios), máximo LIMITE_RESUMEN caracteres; nunca vacía."""
    texto = una_linea(resumen or "", LIMITE_RESUMEN)
    return texto or RESUMEN_NO_DISPONIBLE


def texto_aviso_libre(numero_cliente: str, resumen: str) -> str:
    return (
        "Un cliente pidió hablar con una persona del equipo.\n"
        f"Teléfono del cliente: {numero_cliente}\n"
        f"Solicitud: {resumen}"
    )


def avisar_derivacion(
    pedidos: Pedidos,
    numero_dueno: str | None,
    numero_cliente: str,
    resumen: str | None,
    ahora: float,
    enviar_texto_con_wamid_fn,
    enviar_plantilla_fn=None,
    plantilla_nombre: str | None = None,
    plantilla_idioma: str | None = None,
) -> bool:
    """Devuelve True si se envió un aviso; False si no hay dueño configurado,
    si ya se avisó por este cliente en los últimos 30 minutos o si el envío falló."""
    if not numero_dueno:
        return False

    cliente_enmascarado = enmascarar_numero(numero_cliente)
    if not pedidos.reservar_aviso_derivacion(numero_cliente, ahora, VENTANA_ANTIRREPETICION_SEGUNDOS):
        logger.info(
            "Aviso de derivación omitido: ya se avisó al dueño por este cliente en los últimos "
            "30 minutos (cliente=%s).",
            cliente_enmascarado,
        )
        return False

    resumen_saneado = resumen_para_aviso(resumen)
    if plantilla_nombre and plantilla_idioma and enviar_plantilla_fn is not None:
        canal = "plantilla"
        ok, wamid = enviar_plantilla_fn(
            numero_dueno, plantilla_nombre, plantilla_idioma, [numero_cliente, resumen_saneado]
        )
    else:
        canal = "texto libre"
        ok, wamid = enviar_texto_con_wamid_fn(numero_dueno, texto_aviso_libre(numero_cliente, resumen_saneado))

    if not ok:
        pedidos.liberar_aviso_derivacion(numero_cliente, ahora)
        logger.warning(
            "No se pudo enviar el aviso de derivación al dueño (%s, cliente=%s).",
            canal, cliente_enmascarado,
        )
        return False

    if wamid:
        pedidos.fijar_wamid_aviso_derivacion(numero_cliente, wamid)
    logger.info("Aviso de derivación enviado al dueño por %s (cliente=%s).", canal, cliente_enmascarado)
    return True
