import logging
import sqlite3

import pytest

import basedatos


def test_ejecutar_aplica_wal_y_busy_timeout(tmp_path):
    ruta_bd = tmp_path / "prueba.db"

    modo = basedatos.ejecutar(ruta_bd, lambda c: c.execute("PRAGMA journal_mode").fetchone()[0])
    timeout_ms = basedatos.ejecutar(ruta_bd, lambda c: c.execute("PRAGMA busy_timeout").fetchone()[0])

    assert modo.lower() == "wal"
    assert timeout_ms == basedatos.BUSY_TIMEOUT_MS


def test_ejecutar_devuelve_el_resultado_de_la_operacion_y_hace_commit(tmp_path):
    ruta_bd = tmp_path / "prueba.db"
    basedatos.ejecutar(ruta_bd, lambda c: c.execute("CREATE TABLE t (x INTEGER)"))

    id_insertado = basedatos.ejecutar(ruta_bd, lambda c: c.execute("INSERT INTO t VALUES (1)").lastrowid)
    filas = basedatos.ejecutar(ruta_bd, lambda c: c.execute("SELECT x FROM t").fetchall())

    assert id_insertado == 1
    assert filas == [(1,)]


def test_ejecutar_reintenta_ante_database_is_locked_y_termina_en_exito(tmp_path, monkeypatch, caplog):
    ruta_bd = tmp_path / "prueba.db"
    llamadas = {"n": 0}

    def operacion(conexion):
        llamadas["n"] += 1
        if llamadas["n"] < 2:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    monkeypatch.setattr(basedatos.time, "sleep", lambda segundos: None)
    caplog.set_level(logging.WARNING, logger="basedatos")

    resultado = basedatos.ejecutar(ruta_bd, operacion)

    assert resultado == "ok"
    assert llamadas["n"] == 2
    assert any("bloqueada" in r.getMessage().lower() for r in caplog.records)


def test_ejecutar_relanza_tras_agotar_los_intentos_sin_perder_el_error(tmp_path, monkeypatch):
    ruta_bd = tmp_path / "prueba.db"
    monkeypatch.setattr(basedatos.time, "sleep", lambda segundos: None)
    llamadas = {"n": 0}

    def operacion(conexion):
        llamadas["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError):
        basedatos.ejecutar(ruta_bd, operacion)

    assert llamadas["n"] == basedatos.INTENTOS_ANTE_BLOQUEO


def test_ejecutar_no_reintenta_otros_errores_operacionales(tmp_path):
    ruta_bd = tmp_path / "prueba.db"
    llamadas = {"n": 0}

    def operacion(conexion):
        llamadas["n"] += 1
        raise sqlite3.OperationalError("no such table: x")

    with pytest.raises(sqlite3.OperationalError):
        basedatos.ejecutar(ruta_bd, operacion)

    assert llamadas["n"] == 1
