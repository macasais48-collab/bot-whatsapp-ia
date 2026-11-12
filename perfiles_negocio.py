"""Resolución del perfil de negocio activo y de sus recursos — compartida entre
webhook.py y gestionar_pedido.py, que nunca debe importar webhook.py (no tiene
por qué cargar Flask solo para resolver una ruta de archivo).

Perfiles incluidos en este repositorio (PERFILES_NEGOCIO/RECURSOS_NEGOCIO) vs.
perfiles de cliente (prospectos, demos privadas) resueltos por convención
desde clientes/<clave>/ — ver RAIZ_CLIENTES: sus archivos NUNCA viven en este
repositorio ni en la imagen Docker, se montan como volumen de solo lectura en
docker-compose.yml."""
import re
from pathlib import Path

from env import obtener_env

PERFIL_NEGOCIO_POR_DEFECTO = "panaderia"
PERFILES_NEGOCIO = {
    "panaderia": Path(__file__).parent / "negocio.md",
    "camilo": Path(__file__).parent / "perfil_camilo.md",
    "tamales": Path(__file__).parent / "perfil_tamales.md",
}
RECURSOS_NEGOCIO = {
    "panaderia": Path(__file__).parent / "recursos_panaderia.json",
    "camilo": Path(__file__).parent / "recursos_camilo.json",
    "tamales": Path(__file__).parent / "recursos_tamales.json",
}

RAIZ_CLIENTES = Path(__file__).parent / "clientes"
PATRON_CLAVE_PERFIL_CLIENTE = re.compile(r"^[a-z0-9_]{1,40}$")


def resolver_clave_perfil_activo() -> str:
    clave = obtener_env("PERFIL_NEGOCIO") or PERFIL_NEGOCIO_POR_DEFECTO
    if clave in PERFILES_NEGOCIO or PATRON_CLAVE_PERFIL_CLIENTE.match(clave):
        return clave
    raise ValueError(
        "PERFIL_NEGOCIO no es válido. Debe ser uno de: "
        + ", ".join(sorted(PERFILES_NEGOCIO))
        + ", o la clave de un perfil de cliente (solo minúsculas, números y guion bajo, hasta "
        "40 caracteres) con su carpeta clientes/<clave>/ correspondiente."
    )


def ruta_perfil_cliente(clave: str, nombre_archivo: str) -> Path:
    ruta = (RAIZ_CLIENTES / clave / nombre_archivo).resolve()
    if not ruta.is_relative_to(RAIZ_CLIENTES.resolve()):
        # Defensa en profundidad: con PATRON_CLAVE_PERFIL_CLIENTE esto no debería
        # ser alcanzable (la clave nunca puede traer "/" ni ".."), pero cubre
        # también el caso de un enlace simbólico dentro de clientes/ que apunte
        # fuera de esa carpeta.
        raise ValueError(f"Ruta de perfil de cliente fuera de {RAIZ_CLIENTES.name}/: '{clave}'.")
    if not ruta.is_file():
        raise ValueError(
            f"El perfil '{clave}' requiere clientes/{clave}/{nombre_archivo} "
            "(no incluido en este repositorio; pídeselo al desarrollador)."
        )
    return ruta


def ruta_perfil_para_clave(clave: str) -> Path:
    if clave in PERFILES_NEGOCIO:
        return PERFILES_NEGOCIO[clave]
    return ruta_perfil_cliente(clave, f"perfil_{clave}.md")


def ruta_recursos_para_clave(clave: str) -> Path:
    if clave in RECURSOS_NEGOCIO:
        return RECURSOS_NEGOCIO[clave]
    return ruta_perfil_cliente(clave, f"recursos_{clave}.json")


def resolver_ruta_perfil_activo() -> Path:
    return ruta_perfil_para_clave(resolver_clave_perfil_activo())


def resolver_ruta_recursos_activo() -> Path:
    return ruta_recursos_para_clave(resolver_clave_perfil_activo())
