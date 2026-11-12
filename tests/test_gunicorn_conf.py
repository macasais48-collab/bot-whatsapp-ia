import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _cargar_gunicorn_conf():
    ruta = Path(__file__).parent.parent / "gunicorn.conf.py"
    especificacion = importlib.util.spec_from_file_location("gunicorn_conf_prueba", ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def test_post_worker_init_arranca_el_reporte_semanal_una_vez():
    conf = _cargar_gunicorn_conf()
    llamadas = []
    worker = SimpleNamespace(wsgi=SimpleNamespace(extensions={"iniciar_reporte_semanal": lambda: llamadas.append(1)}))

    conf.post_worker_init(worker)

    assert llamadas == [1]


def test_post_worker_init_sin_la_extension_no_falla():
    conf = _cargar_gunicorn_conf()

    conf.post_worker_init(SimpleNamespace(wsgi=SimpleNamespace(extensions={})))
    conf.post_worker_init(SimpleNamespace())
