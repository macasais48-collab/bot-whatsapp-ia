import sys
import time

import estado_pedido
import perfiles_negocio
import reporte_semanal
from env import obtener_env
from mensajes_enriquecidos import enviar_plantilla, enviar_texto_con_wamid
from pago_pedido import confirmar_pago, rechazar_pago
from pedidos import ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR, Pedidos
from recursos import cargar_recursos
from telefono import enmascarar_numero, normalizar_numero
from whatsapp import enviar_texto


def _domicilio_del_pedido(pedido: dict) -> dict:
    # El aviso de pedido nuevo necesita las zonas de domicilio para armar el
    # resumen; se resuelven por el perfil guardado en el propio pedido, nunca
    # importando webhook.py (este script nunca debe depender de Flask).
    try:
        ruta_recursos = perfiles_negocio.ruta_recursos_para_clave(pedido["perfil"])
        return cargar_recursos(ruta_recursos).get("domicilio", {})
    except (KeyError, ValueError):
        return {}


def _formatear_pesos(valor: int) -> str:
    return f"${valor:,}".replace(",", ".")


def _describir(pedido: dict) -> str:
    total = _formatear_pesos(pedido["total"] or 0)
    return f'#{pedido["id"]} — cliente {enmascarar_numero(pedido["numero_cliente"])} — total {total}'


def listar(pedidos: Pedidos) -> None:
    for estado, titulo in (
        (ESTADO_PAGO_PENDIENTE, "pago_pendiente"),
        (ESTADO_PAGO_POR_VERIFICAR, "pago_por_verificar"),
    ):
        print(f"Pedidos en {titulo}:")
        filas = pedidos.listar_por_estados([estado])
        if not filas:
            print("  (ninguno)")
        for pedido in filas:
            print(f"  {_describir(pedido)}")


def listar_estados(pedidos: Pedidos) -> None:
    # Mismo listado que el dueño ve con "pedidos" por WhatsApp, completo (sin
    # paginación) y con el teléfono siempre enmascarado.
    print("Pedidos activos de entrega (del más antiguo al más reciente):")
    activos = pedidos.listar_activos_entrega()
    if not activos:
        print("  (ninguno)")
    for pedido in activos:
        entrega = "domicilio" if pedido["tipo_entrega"] == "domicilio" else "recoger"
        estado = estado_pedido.ETIQUETA_ESTADO.get(pedido["estado_entrega"], pedido["estado_entrega"])
        print(f"  {_describir(pedido)} — {entrega} — {estado}")


def avanzar_estado(pedidos: Pedidos, pedido_id: int) -> int:
    pedido = pedidos.obtener(pedido_id)
    if pedido is None:
        print(f"No existe un pedido con el número {pedido_id}.")
        return 1
    estado_nuevo = estado_pedido.siguiente_estado(pedido)
    if estado_nuevo is None:
        print(f"El pedido #{pedido_id} no tiene un siguiente paso de entrega (estado de entrega: "
              f'{pedido["estado_entrega"] or "sin confirmar"}).')
        return 1

    accion = f"marcar como {estado_pedido.ETIQUETA_ESTADO[estado_nuevo].lower()}"
    if not _confirmar_con_el_usuario(pedido, accion):
        print("Cancelado, no se hizo ningún cambio.")
        return 0
    print(estado_pedido.avanzar_estado(pedidos, pedido_id, estado_nuevo, time.time(), enviar_texto_con_wamid))
    return 0


def _confirmar_con_el_usuario(pedido: dict, accion: str) -> bool:
    print(f'{_describir(pedido)} — estado actual: {pedido["estado"]}')
    respuesta = input(f'¿Confirma "{accion}" sobre este pedido? (si/no): ').strip().lower()
    return respuesta in ("si", "s")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pedidos = Pedidos()

    if not argv or argv[0] == "listar":
        listar(pedidos)
        return 0

    if argv[0] in ("confirmar", "no-llego") and len(argv) == 2:
        try:
            pedido_id = int(argv[1])
        except ValueError:
            print(f"'{argv[1]}' no es un número de pedido válido.")
            return 1

        pedido = pedidos.obtener(pedido_id)
        if pedido is None:
            print(f"No existe un pedido con el número {pedido_id}.")
            return 1

        accion = "confirmar pago" if argv[0] == "confirmar" else "marcar como no recibido"
        if not _confirmar_con_el_usuario(pedido, accion):
            print("Cancelado, no se hizo ningún cambio.")
            return 0

        ahora = time.time()
        if argv[0] == "confirmar":
            numero_dueno_valor = obtener_env("NUMERO_DUENO")
            print(confirmar_pago(
                pedidos, pedido_id, ahora, enviar_texto,
                domicilio=_domicilio_del_pedido(pedido),
                numero_dueno=normalizar_numero(numero_dueno_valor) if numero_dueno_valor else None,
                enviar_plantilla_fn=enviar_plantilla,
                plantilla_nombre=obtener_env("PLANTILLA_AVISO_PEDIDO_NUEVO_NOMBRE") or None,
                plantilla_idioma=obtener_env("PLANTILLA_AVISO_PEDIDO_NUEVO_IDIOMA") or None,
            ))
        else:
            print(rechazar_pago(pedidos, pedido_id, ahora, enviar_texto))
        return 0

    if argv == ["reporte"]:
        # Solo imprime el reporte de la semana en curso (el mismo que recibe el
        # dueño al escribir "reporte"); nunca envía nada por WhatsApp.
        print(reporte_semanal.texto_semana_en_curso(pedidos, time.time()))
        return 0

    if argv[0] == "estado" and argv[1:] == ["listar"]:
        listar_estados(pedidos)
        return 0

    if argv[0] == "estado" and len(argv) == 3 and argv[1] == "avanzar":
        try:
            pedido_id = int(argv[2])
        except ValueError:
            print(f"'{argv[2]}' no es un número de pedido válido.")
            return 1
        return avanzar_estado(pedidos, pedido_id)

    print(
        "Uso: gestionar_pedido.py [listar | confirmar <id> | no-llego <id> | "
        "estado listar | estado avanzar <id> | reporte]"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
