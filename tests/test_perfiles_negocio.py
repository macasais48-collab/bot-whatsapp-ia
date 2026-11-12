import os

import pytest

import perfiles_negocio
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


def test_resolver_ruta_perfil_activo_usa_panaderia_si_no_esta_definida(monkeypatch):
    monkeypatch.delenv("PERFIL_NEGOCIO", raising=False)

    assert (
        perfiles_negocio.resolver_ruta_perfil_activo()
        == perfiles_negocio.PERFILES_NEGOCIO[perfiles_negocio.PERFIL_NEGOCIO_POR_DEFECTO]
    )


def test_resolver_ruta_perfil_activo_carga_el_perfil_de_camilo(monkeypatch):
    monkeypatch.setenv("PERFIL_NEGOCIO", "camilo")

    assert perfiles_negocio.resolver_ruta_perfil_activo() == perfiles_negocio.PERFILES_NEGOCIO["camilo"]


def test_resolver_ruta_perfil_activo_falla_con_valor_desconocido(monkeypatch):
    monkeypatch.setenv("PERFIL_NEGOCIO", "no-existe")

    with pytest.raises(ValueError) as info:
        perfiles_negocio.resolver_ruta_perfil_activo()

    assert "PERFIL_NEGOCIO no es válido" in str(info.value)
    assert "panaderia" in str(info.value)
    assert "camilo" in str(info.value)


def test_el_mecanismo_generico_carga_un_perfil_de_cliente_ficticio(tmp_path, monkeypatch):
    monkeypatch.setattr(perfiles_negocio, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", CLAVE_DE_PRUEBA)
    _escribir_perfil_de_prueba(tmp_path)

    ruta_negocio = perfiles_negocio.resolver_ruta_perfil_activo()
    ruta_recursos = perfiles_negocio.resolver_ruta_recursos_activo()

    assert ruta_negocio.name == f"perfil_{CLAVE_DE_PRUEBA}.md"
    assert ruta_negocio.is_relative_to(tmp_path)
    recursos = cargar_recursos(ruta_recursos)
    assert recursos["catalogo"]["producto_prueba"]["precio"] == 1000


def test_ruta_recursos_para_clave_resuelve_por_una_clave_explicita(tmp_path, monkeypatch):
    # Lo que usa gestionar_pedido.py: resolver por el perfil guardado en el
    # pedido, sin depender de PERFIL_NEGOCIO ni de ningún estado "activo".
    monkeypatch.setattr(perfiles_negocio, "RAIZ_CLIENTES", tmp_path)
    _escribir_perfil_de_prueba(tmp_path)

    ruta = perfiles_negocio.ruta_recursos_para_clave(CLAVE_DE_PRUEBA)

    assert ruta.name == f"recursos_{CLAVE_DE_PRUEBA}.json"


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
    monkeypatch.setattr(perfiles_negocio, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", clave_invalida)

    with pytest.raises(ValueError):
        perfiles_negocio.resolver_clave_perfil_activo()


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

    monkeypatch.setattr(perfiles_negocio, "RAIZ_CLIENTES", raiz_clientes)

    with pytest.raises(ValueError, match="fuera de"):
        perfiles_negocio.ruta_perfil_cliente(CLAVE_DE_PRUEBA, f"perfil_{CLAVE_DE_PRUEBA}.md")


def test_error_claro_si_falta_la_carpeta_del_cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(perfiles_negocio, "RAIZ_CLIENTES", tmp_path)
    monkeypatch.setenv("PERFIL_NEGOCIO", CLAVE_DE_PRUEBA)

    with pytest.raises(ValueError, match=f"clientes/{CLAVE_DE_PRUEBA}/"):
        perfiles_negocio.resolver_ruta_perfil_activo()
