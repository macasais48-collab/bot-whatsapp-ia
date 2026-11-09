from pathlib import Path


def test_docker_compose_monta_la_carpeta_de_clientes_de_solo_lectura():
    # clientes/ guarda datos reales de terceros (perfiles de prospectos, demos
    # privadas) que nunca entran a la imagen: llegan al contenedor solo por
    # este volumen de solo lectura (ver webhook.RAIZ_CLIENTES).
    ruta_compose = Path(__file__).parent.parent / "docker-compose.yml"
    contenido = ruta_compose.read_text(encoding="utf-8")

    assert "./clientes:/app/clientes:ro" in contenido, (
        "docker-compose.yml debe montar ./clientes como volumen de solo lectura en "
        "/app/clientes, para que los perfiles de clientes lleguen al contenedor sin "
        "copiarse nunca a la imagen."
    )
