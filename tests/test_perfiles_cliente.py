import os

import pytest

import webhook
from recursos import cargar_recursos

CLAVE_DE_PRUEBA = "cliente_prueba"


def _escribir_perfil_de_prueba(raiz_clientes, clave=CLAVE_DE_PRUEBA):
    carpeta = raiz_clientes / clave
    carpeta.mkdir(parents=True)
    (carpeta / f"perfil_{clave}.md").write_text(
        "# Negocio de prueba\n\nContenido ficticio, solo para pruebas automáticas.\n",
        encoding="utf-8",
    )
    (carpeta / f"recursos_{clave}.json").write_text(
        '{"catalogo": {"producto_prueba": '
        '{"nombre": "Producto de prueba", "precio": 1000, "unidad": "unidad"}}}',
        encoding="utf-8",
    )
    return carpeta


def test_el_mecanismo_generico_carga_un_perfil_de_cliente_ficticio(tmp_path, monkeypatch):
    monkeypatch.setattr(webhook, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", CLAVE_DE_PRUEBA)
    _escribir_perfil_de_prueba(tmp_path)

    ruta_negocio = webhook._resolver_ruta_negocio()
    ruta_recursos = webhook._resolver_ruta_recursos()

    assert ruta_negocio.name == f"perfil_{CLAVE_DE_PRUEBA}.md"
    assert ruta_negocio.is_relative_to(tmp_path)
    recursos = cargar_recursos(ruta_recursos)
    assert recursos["catalogo"]["producto_prueba"]["precio"] == 1000


@pytest.mark.parametrize(
    "clave_invalida",
    [
        "../etc",
        "cliente/../../etc",
        "CLIENTE_PRUEBA",
        "cliente prueba",
        "a" * 41,
    ],
)
def test_el_patron_rechaza_intentos_de_salirse_de_la_carpeta(tmp_path, monkeypatch, clave_invalida):
    monkeypatch.setattr(webhook, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", clave_invalida)

    with pytest.raises(ValueError):
        webhook._resolver_clave_perfil()


def test_is_relative_to_bloquea_un_enlace_simbolico_que_sale_de_clientes(tmp_path, monkeypatch):
    raiz_clientes = tmp_path / "clientes"
    raiz_clientes.mkdir()
    fuera_de_clientes = tmp_path / "fuera"
    fuera_de_clientes.mkdir()
    (fuera_de_clientes / f"perfil_{CLAVE_DE_PRUEBA}.md").write_text("fuera", encoding="utf-8")

    enlace = raiz_clientes / CLAVE_DE_PRUEBA
    try:
        os.symlink(fuera_de_clientes, enlace, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Esta máquina no permite crear enlaces simbólicos sin privilegios elevados.")

    monkeypatch.setattr(webhook, "RAIZ_CLIENTES", raiz_clientes)

    with pytest.raises(ValueError, match="fuera de"):
        webhook._ruta_perfil_cliente(CLAVE_DE_PRUEBA, f"perfil_{CLAVE_DE_PRUEBA}.md")


def test_error_claro_si_falta_la_carpeta_del_cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(webhook, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", CLAVE_DE_PRUEBA)

    with pytest.raises(ValueError, match=f"clientes/{CLAVE_DE_PRUEBA}/"):
        webhook._resolver_ruta_negocio()
