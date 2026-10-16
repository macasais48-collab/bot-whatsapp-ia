import almacenamiento
from almacenamiento import HistorialSQLite


def crear_historial(tmp_path):
    return HistorialSQLite(tmp_path / "prueba.db")


def test_guarda_y_obtiene_mensajes_en_orden_cronologico(tmp_path):
    historial = crear_historial(tmp_path)

    historial.agregar("conv1", "user", "Hola")
    historial.agregar("conv1", "assistant", "Hola, ¿en qué te ayudo?")
    historial.agregar("conv1", "user", "¿A qué hora abren?")

    mensajes = historial.obtener("conv1", limite=10)

    assert mensajes == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
        {"role": "user", "content": "¿A qué hora abren?"},
    ]


def test_obtener_respeta_el_limite_devolviendo_los_mas_recientes(tmp_path):
    historial = crear_historial(tmp_path)

    for i in range(5):
        historial.agregar("conv1", "user", f"mensaje {i}")

    mensajes = historial.obtener("conv1", limite=2)

    assert mensajes == [
        {"role": "user", "content": "mensaje 3"},
        {"role": "user", "content": "mensaje 4"},
    ]


def test_obtener_con_limite_cero_devuelve_lista_vacia(tmp_path):
    historial = crear_historial(tmp_path)
    historial.agregar("conv1", "user", "hola")

    assert historial.obtener("conv1", limite=0) == []


def test_conversaciones_distintas_no_se_mezclan(tmp_path):
    historial = crear_historial(tmp_path)

    historial.agregar("conv1", "user", "mensaje de conv1")
    historial.agregar("conv2", "user", "mensaje de conv2")

    assert historial.obtener("conv1", limite=10) == [
        {"role": "user", "content": "mensaje de conv1"}
    ]
    assert historial.obtener("conv2", limite=10) == [
        {"role": "user", "content": "mensaje de conv2"}
    ]


def test_historial_persiste_entre_instancias_del_mismo_archivo(tmp_path):
    ruta_bd = tmp_path / "persistente.db"

    HistorialSQLite(ruta_bd).agregar("conv1", "user", "hola")
    historial_reabierto = HistorialSQLite(ruta_bd)

    assert historial_reabierto.obtener("conv1", limite=10) == [
        {"role": "user", "content": "hola"}
    ]


def test_marcar_si_nuevo_es_true_la_primera_vez_y_false_despues(tmp_path):
    historial = crear_historial(tmp_path)

    assert historial.marcar_si_nuevo("wamid_123") is True
    assert historial.marcar_si_nuevo("wamid_123") is False


def test_marcar_si_nuevo_distingue_ids_distintos(tmp_path):
    historial = crear_historial(tmp_path)

    assert historial.marcar_si_nuevo("wamid_1") is True
    assert historial.marcar_si_nuevo("wamid_2") is True
    assert historial.marcar_si_nuevo("wamid_1") is False


def test_usa_ruta_bd_de_la_variable_de_entorno_si_esta_definida(tmp_path, monkeypatch):
    ruta_personalizada = tmp_path / "personalizada.db"
    monkeypatch.setenv("RUTA_BD", str(ruta_personalizada))

    historial = HistorialSQLite()

    assert historial._ruta_bd == str(ruta_personalizada)
    assert ruta_personalizada.exists()


def test_usa_la_ruta_por_defecto_si_no_hay_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.delenv("RUTA_BD", raising=False)
    ruta_por_defecto_de_prueba = tmp_path / "por_defecto.db"
    monkeypatch.setattr(almacenamiento, "RUTA_BD_POR_DEFECTO", ruta_por_defecto_de_prueba)

    historial = HistorialSQLite()

    assert historial._ruta_bd == str(ruta_por_defecto_de_prueba)
    assert ruta_por_defecto_de_prueba.exists()
