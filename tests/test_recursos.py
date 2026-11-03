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
    ruta = _escribir(tmp_path, "recursos.json", {"botones": {}})

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "botones" in str(info.value)


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


FIRMA_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
FIRMA_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _escribir_imagen(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    return ruta


def test_carga_una_imagen_jpeg_valida(tmp_path):
    _escribir_imagen(tmp_path, "tortas.jpg", FIRMA_JPEG)
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"catalogo_tortas": {"descripcion": "Catálogo de tortas.", "archivo": "tortas.jpg"}}},
    )

    recursos = cargar_recursos(ruta)

    assert recursos["imagenes"]["catalogo_tortas"]["clave"] == "catalogo_tortas"
    assert recursos["imagenes"]["catalogo_tortas"]["descripcion"] == "Catálogo de tortas."
    assert recursos["imagenes"]["catalogo_tortas"]["archivo"].name == "tortas.jpg"


def test_carga_una_imagen_png_valida(tmp_path):
    _escribir_imagen(tmp_path, "vitrina.png", FIRMA_PNG)
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"vitrina": {"descripcion": "Vitrina de la panadería.", "archivo": "vitrina.png"}}},
    )

    recursos = cargar_recursos(ruta)

    assert recursos["imagenes"]["vitrina"]["archivo"].name == "vitrina.png"


def test_falla_si_el_archivo_de_imagen_no_existe(tmp_path):
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"pan": {"descripcion": "Pan del día.", "archivo": "no_existe.jpg"}}},
    )

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "no existe" in str(info.value)


def test_falla_si_la_extension_de_imagen_no_es_jpg_ni_png(tmp_path):
    _escribir_imagen(tmp_path, "pan.gif", FIRMA_JPEG)
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"pan": {"descripcion": "Pan del día.", "archivo": "pan.gif"}}},
    )

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "jpg" in str(info.value).lower()


def test_falla_si_el_contenido_del_archivo_no_es_jpeg_ni_png(tmp_path):
    _escribir_imagen(tmp_path, "pan.jpg", b"esto no es una imagen")
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"pan": {"descripcion": "Pan del día.", "archivo": "pan.jpg"}}},
    )

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "válido" in str(info.value).lower()


def test_falla_si_la_imagen_supera_el_tamano_maximo(tmp_path):
    _escribir_imagen(tmp_path, "pan.jpg", FIRMA_JPEG + b"\x00" * (5 * 1024 * 1024))
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"pan": {"descripcion": "Pan del día.", "archivo": "pan.jpg"}}},
    )

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "5 MB" in str(info.value)


def test_falla_con_descripcion_de_imagen_vacia(tmp_path):
    _escribir_imagen(tmp_path, "pan.jpg", FIRMA_JPEG)
    ruta = _escribir(
        tmp_path,
        "recursos.json",
        {"imagenes": {"pan": {"descripcion": "", "archivo": "pan.jpg"}}},
    )

    with pytest.raises(ValueError) as info:
        cargar_recursos(ruta)

    assert "descripcion" in str(info.value)
