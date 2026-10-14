from llm.base import ProveedorIA


class ProveedorOpenAI(ProveedorIA):
    def __init__(self) -> None:
        # pendiente para clientes que usen OpenAI
        raise NotImplementedError("Proveedor OpenAI pendiente para clientes que usen OpenAI.")

    def responder(self, sistema: str, mensajes: list[dict]) -> str:
        raise NotImplementedError("Proveedor OpenAI pendiente para clientes que usen OpenAI.")
