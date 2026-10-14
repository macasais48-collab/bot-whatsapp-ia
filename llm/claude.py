from anthropic import Anthropic

from env import obtener_env
from llm.base import ProveedorIA


class ProveedorClaude(ProveedorIA):
    def __init__(self) -> None:
        api_key = obtener_env("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada en el entorno.")

        modelo = obtener_env("MODELO_IA")
        if not modelo:
            raise ValueError("MODELO_IA no está configurada en el entorno.")

        self._modelo = modelo
        self._cliente = Anthropic(api_key=api_key)

    def responder(self, sistema: str, mensajes: list[dict]) -> str:
        respuesta = self._cliente.messages.create(
            model=self._modelo,
            max_tokens=1024,
            system=sistema,
            messages=mensajes,
        )
        return "".join(
            bloque.text for bloque in respuesta.content if bloque.type == "text"
        )
