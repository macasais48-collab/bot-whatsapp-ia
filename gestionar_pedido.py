import sys
import time

from pago_pedido import confirmar_pago, rechazar_pago
from pedidos import ESTADO_PAGO_PENDIENTE, ESTADO_PAGO_POR_VERIFICAR, Pedidos
from telefono import enmascarar_numero
from whatsapp import enviar_texto


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

        funcion = confirmar_pago if argv[0] == "confirmar" else rechazar_pago
        print(funcion(pedidos, pedido_id, time.time(), enviar_texto))
        return 0

    print("Uso: gestionar_pedido.py [listar | confirmar <id> | no-llego <id>]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
