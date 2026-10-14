from abc import ABC, abstractmethod


class ProveedorIA(ABC):
    @abstractmethod
    def responder(self, sistema: str, mensajes: list[dict]) -> str:
        ...
