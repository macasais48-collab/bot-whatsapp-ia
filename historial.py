from abc import ABC, abstractmethod


class Historial(ABC):
    @abstractmethod
    def obtener(self, id_conversacion: str, limite: int) -> list[dict]:
        ...

    @abstractmethod
    def agregar(self, id_conversacion: str, rol: str, texto: str) -> None:
        ...


class HistorialMemoria(Historial):
    def __init__(self) -> None:
        self._conversaciones: dict[str, list[dict]] = {}

    def obtener(self, id_conversacion: str, limite: int) -> list[dict]:
        mensajes = self._conversaciones.get(id_conversacion, [])
        if limite <= 0:
            return []
        return mensajes[-limite:]

    def agregar(self, id_conversacion: str, rol: str, texto: str) -> None:
        self._conversaciones.setdefault(id_conversacion, []).append(
            {"role": rol, "content": texto}
        )
