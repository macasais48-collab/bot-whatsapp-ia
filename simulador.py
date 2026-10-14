from dotenv import load_dotenv

from almacenamiento import HistorialSQLite
from cerebro import Cerebro
from llm import crear_proveedor_ia

ID_CONVERSACION = "consola"
COMANDOS_SALIDA = {"/salir", "salir", "exit", "quit"}


def main() -> None:
    load_dotenv()

    cerebro = Cerebro(crear_proveedor_ia(), HistorialSQLite())

    print("Simulador de Panadería San Roque. Escribe '/salir' para terminar.\n")

    while True:
        try:
            texto = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not texto:
            continue

        if texto.lower() in COMANDOS_SALIDA:
            print("Hasta luego.")
            break

        respuesta = cerebro.responder(ID_CONVERSACION, texto)
        print(f"Bot: {respuesta.texto}")
        if respuesta.derivar:
            print("[Este mensaje se derivaría a una persona.]")


if __name__ == "__main__":
    main()
