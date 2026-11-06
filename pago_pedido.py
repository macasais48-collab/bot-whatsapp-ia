import logging

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


def confirmar_pago(pedidos: Pedidos, pedido_id: int, ahora: float, enviar_texto_fn) -> str:
    pedido, error = _validar_pedido_en_verificacion(pedidos, pedido_id)
    if error is not None:
        return error

    pedidos.marcar_pagado(pedido_id, ahora)
    enviar_texto_fn(pedido["numero_cliente"], MENSAJE_PAGO_CONFIRMADO.format(id=pedido_id))
    logger.info(
        "Pedido #%s marcado como pagado (remitente=%s)",
        pedido_id, enmascarar_numero(pedido["numero_cliente"]),
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
