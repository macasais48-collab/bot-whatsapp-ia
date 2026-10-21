from pathlib import Path

from webhook import PERFILES_NEGOCIO


def test_dockerfile_copia_todos_los_archivos_de_perfiles_de_negocio():
    ruta_dockerfile = Path(__file__).parent.parent / "Dockerfile"
    contenido = ruta_dockerfile.read_text(encoding="utf-8")

    for ruta_perfil in PERFILES_NEGOCIO.values():
        assert ruta_perfil.name in contenido, (
            f"{ruta_perfil.name} no aparece en el Dockerfile: agrégalo a la línea "
            "COPY para que no falte dentro de la imagen (ver incidente del 21/10/2026, "
            "donde faltó perfil_camilo.md y el contenedor entró en crash-loop)."
        )
