import logging

from pedido_resumen import entrega_una_linea, formatear_pesos, resumen_productos_una_linea
from pedidos import ESTADO_PAGO_POR_VERIFICAR, Pedidos
from telefono import enmascarar_numero

logger = logging.getLogger(__name__)

PREFIJO_BOTON_PAGO_RECIBIDO = "pago_recibido_"
PREFIJO_BOTON_PAGO_NO_LLEGO = "pago_no_llego_"

MENSAJE_PAGO_CONFIRMADO = "Su pago fue confirmado. Su pedido #{id} está en preparación."
MENSAJE_PAGO_NO_LLEGO = (
    "Todavía no vemos su pago reflejado. Puede enviar otro comprobante o escribir "
    "*asesor* para hablar con una persona."
)

_ETIQUETA_METODO_PAGO = {"efectivo": "Efectivo", "qr": "QR / transferencia"}


def avisar_pedido_nuevo(
    pedidos: Pedidos,
    numero_dueno: str | None,
    pedido: dict,
    domicilio: dict,
    ahora: float,
    enviar_texto_fn,
    enviar_plantilla_fn=None,
    plantilla_nombre: str | None = None,
    plantilla_idioma: str | None = None,
) -> None:
    """Avisa al negocio que un pedido quedó confirmado (efectivo o QR pagado) —
    hoy solo se avisaba cuando había un comprobante por verificar; un pedido en
    efectivo nunca llegaba a notificarse. El teléfono del cliente va COMPLETO
    en el contenido del aviso (excepción deliberada: el negocio necesita poder
    contactarlo para coordinar la entrega) — en el log siempre enmascarado."""
    if not numero_dueno:
        return

    metodo_pago = _ETIQUETA_METODO_PAGO.get(pedido.get("metodo_pago"), pedido.get("metodo_pago") or "—")

    if plantilla_nombre and plantilla_idioma and enviar_plantilla_fn is not None:
        ok, wamid = enviar_plantilla_fn(
            numero_dueno,
            plantilla_nombre,
            plantilla_idioma,
            [
                str(pedido["id"]),
                resumen_productos_una_linea(pedido),
                formatear_pesos(pedido["total"]),
                entrega_una_linea(pedido, domicilio),
                metodo_pago,
                pedido["numero_cliente"],
            ],
        )
        if ok and wamid:
            pedidos.registrar_wamid_aviso_dueno(wamid, pedido["id"], "pedido_nuevo", ahora)
        if not ok:
            logger.warning("No se pudo enviar la plantilla de pedido nuevo del pedido #%s.", pedido["id"])
    else:
        enviar_texto_fn(numero_dueno, _resumen_libre(pedido, domicilio, metodo_pago))

    logger.info(
        "Pedido #%s: aviso de pedido nuevo enviado al dueño (cliente=%s)",
        pedido["id"], enmascarar_numero(pedido["numero_cliente"]),
    )


def _resumen_libre(pedido: dict, domicilio: dict, metodo_pago: str) -> str:
    return (
        f'Nuevo pedido #{pedido["id"]} confirmado.\n'
        f"Productos: {resumen_productos_una_linea(pedido)}\n"
        f'Total: {formatear_pesos(pedido["total"])}\n'
        f"Entrega: {entrega_una_linea(pedido, domicilio)}\n"
        f"Pago: {metodo_pago}\n"
        f'Cliente: {pedido["numero_cliente"]}'
    )


def _validar_pedido_en_verificacion(pedidos: Pedidos, pedido_id: int) -> tuple[dict | None, str | None]:
    pedido = pedidos.obtener(pedido_id)
    if pedido is None:
        return None, f"No existe un pedido con el número {pedido_id}."
    if pedido["estado"] != ESTADO_PAGO_POR_VERIFICAR:
        return None, (
            f"El pedido #{pedido_id} no está esperando verificación (estado actual: "
            f'{pedido["estado"]}).'
        )
    return pedido, None


def confirmar_pago(
    pedidos: Pedidos,
    pedido_id: int,
    ahora: float,
    enviar_texto_fn,
    domicilio: dict | None = None,
    numero_dueno: str | None = None,
    enviar_plantilla_fn=None,
    plantilla_nombre: str | None = None,
    plantilla_idioma: str | None = None,
) -> str:
    pedido, error = _validar_pedido_en_verificacion(pedidos, pedido_id)
    if error is not None:
        return error

    pedidos.marcar_pagado(pedido_id, ahora)
    enviar_texto_fn(pedido["numero_cliente"], MENSAJE_PAGO_CONFIRMADO.format(id=pedido_id))
    logger.info(
        "Pedido #%s marcado como pagado (remitente=%s)",
        pedido_id, enmascarar_numero(pedido["numero_cliente"]),
    )

    pedido_actualizado = pedidos.obtener(pedido_id)
    avisar_pedido_nuevo(
        pedidos,
        numero_dueno,
        pedido_actualizado,
        domicilio or {},
        ahora,
        enviar_texto_fn,
        enviar_plantilla_fn=enviar_plantilla_fn,
        plantilla_nombre=plantilla_nombre,
        plantilla_idioma=plantilla_idioma,
    )
    return f"Pedido #{pedido_id} confirmado como pagado."


def rechazar_pago(pedidos: Pedidos, pedido_id: int, ahora: float, enviar_texto_fn) -> str:
    pedido, error = _validar_pedido_en_verificacion(pedidos, pedido_id)
    if error is not None:
        return error

    pedidos.volver_a_pago_pendiente(pedido_id, ahora)
    enviar_texto_fn(pedido["numero_cliente"], MENSAJE_PAGO_NO_LLEGO)
    logger.info(
        "Pedido #%s: pago marcado como no recibido, vuelve a pago_pendiente (remitente=%s)",
        pedido_id, enmascarar_numero(pedido["numero_cliente"]),
    )
    return f"Pedido #{pedido_id} marcado como pago no recibido."
