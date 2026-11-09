from pathlib import Path

from recursos import cargar_recursos
from webhook import PERFILES_NEGOCIO, RECURSOS_NEGOCIO


def test_dockerfile_copia_todos_los_archivos_de_perfiles_de_negocio():
    ruta_dockerfile = Path(__file__).parent.parent / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    for ruta_perfil in PERFILES_NEGOCIO.values():
        assert ruta_perfil.name in contenido, (
            f"{ruta_perfil.name} no aparece en el Dockerfile: agrégalo a la línea "
            "COPY para que no falte dentro de la imagen (ver incidente del 21/10/2026, "
            "donde faltó perfil_camilo.md y el contenedor entró en crash-loop)."
        )


def test_dockerfile_copia_todos_los_archivos_de_recursos_de_negocio():
    ruta_dockerfile = Path(__file__).parent.parent / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    for ruta_recursos in RECURSOS_NEGOCIO.values():
        assert ruta_recursos.name in contenido, (
            f"{ruta_recursos.name} no aparece en el Dockerfile: agrégalo a la línea "
            "COPY para que no falte dentro de la imagen (mismo tipo de error que con "
            "perfil_camilo.md el 21/10/2026)."
        )


def test_dockerfile_copia_los_modulos_de_la_toma_de_pedidos():
    ruta_dockerfile = Path(__file__).parent.parent / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    for nombre_archivo in (
        "pedidos.py",
        "flujo_pedido.py",
        "telefono.py",
        "gunicorn.conf.py",
        "pago_pedido.py",
        "gestionar_pedido.py",
        "basedatos.py",
        "red_meta.py",
    ):
        assert nombre_archivo in contenido, (
            f"{nombre_archivo} no aparece en el Dockerfile: agrégalo a la línea COPY para que no "
            "falte dentro de la imagen (mismo tipo de error que con perfil_camilo.md el 21/10/2026)."
        )


def test_dockerfile_usa_el_config_de_gunicorn_para_el_logging():
    ruta_dockerfile = Path(__file__).parent.parent / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    assert "--config" in contenido and "gunicorn.conf.py" in contenido, (
        "El CMD de gunicorn debe cargar gunicorn.conf.py (--config) para que el logging de la "
        "aplicación (webhook.py, flujo_pedido.py) quede configurado bajo gunicorn."
    )


def test_dockerfile_copia_las_carpetas_de_imagenes_de_los_recursos():
    raiz_proyecto = Path(__file__).parent.parent
    ruta_dockerfile = raiz_proyecto / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    carpetas_de_imagenes = set()
    for ruta_recursos in RECURSOS_NEGOCIO.values():
        datos_recursos = cargar_recursos(ruta_recursos)
        for imagen in datos_recursos.get("imagenes", {}).values():
            ruta_relativa = imagen["archivo"].relative_to(raiz_proyecto)
            carpetas_de_imagenes.add(ruta_relativa.parent.as_posix() + "/")

    for carpeta in carpetas_de_imagenes:
        assert carpeta in contenido, (
            f"{carpeta} no aparece en el Dockerfile: agrégala a una línea COPY para "
            "que las imágenes no falten dentro de la imagen (mismo tipo de error que "
            "con perfil_camilo.md el 21/10/2026)."
        )
