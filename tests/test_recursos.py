import json

import pytest

from recursos import cargar_recursos


def _escribir(tmp_path, nombre, datos):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_carga_un_json_valido_con_ubicacion_y_enlaces(tmp_path):
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {
            "ubicacion": {
                "latitud": 4.73,
                "longitud": -74.26,
                "nombre": "Negocio de ejemplo",
                "direccion": "Calle falsa 123",
            },
            "enlaces": {
                "mapa": {
                    "url": "https://maps.google.com/?q=4.73,-74.26",
                    "texto_boton": "Ver en el mapa",
                    "descripcion": "Así puedes ver nuestra ubicación.",
                }
            },
        },
    )

    recursos = cargar_recursos(ruta)

    assert recursos["ubicacion"]["latitud"] == 4.73
    assert recursos["ubicacion"]["nombre"] == "Negocio de ejemplo"
    assert recursos["enlaces"]["mapa"]["url"] == "https://maps.google.com/?q=4.73,-74.26"


def test_carga_un_json_sin_ubicacion_ni_enlaces(tmp_path):
    ruta = _escribir(tmp_path, "recursos.json", {})

    assert cargar_recursos(ruta) == {}


def test_falla_con_json_mal_formado(tmp_path):
    ruta = tmp_path / "recursos.json"
    ruta.write_text("esto no es json", encoding="utf-8")

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "recursos.json" in str(info.value)


def test_falla_con_clave_raiz_desconocida(tmp_path):
    ruta = _escribir(tmp_path, "recursos.json", {"imagenes": {}})

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "imagenes" in str(info.value)


@pytest.mark.parametrize(
    "ubicacion_invalida,fragmento_error",
    [
        ({"latitud": 99, "longitud": -74.26, "nombre": "x", "direccion": "x"}, "latitud"),
        ({"latitud": 4.73, "longitud": -200, "nombre": "x", "direccion": "x"}, "longitud"),
        ({"latitud": "no-numero", "longitud": -74.26, "nombre": "x", "direccion": "x"}, "latitud"),
        ({"latitud": 4.73, "longitud": -74.26, "nombre": "", "direccion": "x"}, "nombre"),
        ({"latitud": 4.73, "longitud": -74.26, "nombre": "x", "direccion": ""}, "direccion"),
    ],
)
def test_falla_con_ubicacion_invalida(tmp_path, ubicacion_invalida, fragmento_error):
    ruta = _escribir(tmp_path, "recursos.json", {"ubicacion": ubicacion_invalida})

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert fragmento_error in str(info.value)


@pytest.mark.parametrize(
    "enlace_invalido,fragmento_error",
    [
        ({"url": "http://no-es-https.com", "texto_boton": "Ver", "descripcion": "x"}, "url"),
        ({"url": "https://ok.com", "texto_boton": "", "descripcion": "x"}, "texto_boton"),
        (
            {"url": "https://ok.com", "texto_boton": "Texto de botón demasiado largo", "descripcion": "x"},
            "texto_boton",
        ),
        ({"url": "https://ok.com", "texto_boton": "Ver", "descripcion": ""}, "descripcion"),
    ],
)
def test_falla_con_enlace_invalido(tmp_path, enlace_invalido, fragmento_error):
    ruta = _escribir(tmp_path, "recursos.json", {"enlaces": {"prueba": enlace_invalido}})

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert fragmento_error in str(info.value)
