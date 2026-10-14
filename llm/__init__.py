from env import obtener_env
from llm.base import ProveedorIA
from llm.claude import ProveedorClaude
from llm.openai_proveedor import ProveedorOpenAI


def crear_proveedor_ia() -> ProveedorIA:
    proveedor = obtener_env("PROVEEDOR_IA", "claude").lower()
    if proveedor == "claude":
        return ProveedorClaude()
    if proveedor == "openai":
        return ProveedorOpenAI()
    raise ValueError("PROVEEDOR_IA no es válido. Valores permitidos: claude, openai.")
