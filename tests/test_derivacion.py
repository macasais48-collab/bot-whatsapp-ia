import logging

import derivacion
from derivacion import (
    LIMITE_RESUMEN,
    RESUMEN_NO_DISPONIBLE,
    VENTANA_ANTIRREPETICION_SEGUNDOS,
    avisar_derivacion,
    resumen_para_aviso,
)
from pedidos import Pedidos

NUMERO_DUENO = "573005554433"
NUMERO_CLIENTE = "573001112233"


class EnvioFalso:
    def __init__(self, ok=True, wamid="wamid.derivacion-1"):
        self.ok = ok
        self.wamid = wamid
        self.llamadas = []

    def __call__(self, *args, **kwargs):
        self.llamadas.append(args)
        return self.ok, self.wamid


def test_resumen_se_sanea_a_una_sola_linea():
    resumen = resumen_para_aviso("Quiere una cita.\nMascota: Firulais\tperro    mediano\r\nmotivo: control")

    assert "\n" not in resumen and "\r" not in resumen and "\t" not in resumen
    assert "    " not in resumen
    assert resumen == "Quiere una cita. Mascota: Firulais perro mediano motivo: control"


def test_resumen_largo_se_recorta_a_300_caracteres():
    resumen = resumen_para_aviso("palabra " * 100)

    assert len(resumen) == LIMITE_RESUMEN
    assert resumen.endswith("…")


def test_resumen_vacio_usa_el_texto_fijo():
    assert resumen_para_aviso("") == RESUMEN_NO_DISPONIBLE
    assert resumen_para_aviso(None) == RESUMEN_NO_DISPONIBLE
    assert resumen_para_aviso(" \n\t ") == RESUMEN_NO_DISPONIBLE


def test_sin_numero_dueno_no_envia_nada(tmp_path):
    pedidos = Pedidos(tmp_path / "p.db")
    texto = EnvioFalso()

    resultado = avisar_derivacion(pedidos, None, NUMERO_CLIENTE, "x", 1000.0, texto)

    assert resultado is False
    assert texto.llamadas == []


def test_con_plantilla_envia_telefono_completo_y_resumen_saneado(tmp_path):
    pedidos = Pedidos(tmp_path / "p.db")
    texto, plantilla = EnvioFalso(), EnvioFalso(wamid="wamid.plantilla")

    resultado = avisar_derivacion(
        pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "Pide\nuna cita", 1000.0, texto,
        enviar_plantilla_fn=plantilla, plantilla_nombre="plantilla_de_prueba", plantilla_idioma="es",
    )

    assert resultado is True
    assert texto.llamadas == []
    assert plantilla.llamadas == [
        (NUMERO_DUENO, "plantilla_de_prueba", "es", [NUMERO_CLIENTE, "Pide una cita"])
    ]
    assert pedidos.cliente_derivacion_por_wamid("wamid.plantilla") == NUMERO_CLIENTE


def test_sin_plantilla_envia_texto_libre_con_wamid(tmp_path):
    pedidos = Pedidos(tmp_path / "p.db")
    texto, plantilla = EnvioFalso(wamid="wamid.libre"), EnvioFalso()

    resultado = avisar_derivacion(
        pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "Pide una cita", 1000.0, texto,
        enviar_plantilla_fn=plantilla, plantilla_nombre=None, plantilla_idioma=None,
    )

    assert resultado is True
    assert plantilla.llamadas == []
    assert len(texto.llamadas) == 1
    destino, cuerpo = texto.llamadas[0]
    assert destino == NUMERO_DUENO
    assert NUMERO_CLIENTE in cuerpo
    assert "Pide una cita" in cuerpo
    assert pedidos.cliente_derivacion_por_wamid("wamid.libre") == NUMERO_CLIENTE


def test_antirrepeticion_un_aviso_por_cliente_cada_30_minutos(tmp_path):
    pedidos = Pedidos(tmp_path / "p.db")
    texto = EnvioFalso()

    def avisar(ahora, numero=NUMERO_CLIENTE):
        return avisar_derivacion(pedidos, NUMERO_DUENO, numero, "x", ahora, texto)

    assert avisar(1000.0) is True
    assert avisar(1000.0 + 60) is False
    assert avisar(1000.0 + VENTANA_ANTIRREPETICION_SEGUNDOS - 1) is False
    # Otro cliente no se ve afectado.
    assert avisar(1000.0 + 120, numero="573009998877") is True
    # Pasados 30 minutos desde el último aviso, se vuelve a avisar.
    assert avisar(1000.0 + VENTANA_ANTIRREPETICION_SEGUNDOS) is True
    assert len(texto.llamadas) == 3


def test_si_el_envio_falla_no_cuenta_para_la_antirrepeticion(tmp_path, caplog):
    pedidos = Pedidos(tmp_path / "p.db")
    fallido = EnvioFalso(ok=False, wamid=None)
    caplog.set_level(logging.INFO, logger=derivacion.__name__)

    assert avisar_derivacion(pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "x", 1000.0, fallido) is False
    assert "No se pudo enviar el aviso de derivación" in caplog.text

    exitoso = EnvioFalso()
    assert avisar_derivacion(pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "x", 1060.0, exitoso) is True
    assert len(exitoso.llamadas) == 1


def test_logs_enmascaran_el_telefono_y_nunca_incluyen_el_resumen(tmp_path, caplog):
    pedidos = Pedidos(tmp_path / "p.db")
    caplog.set_level(logging.INFO, logger=derivacion.__name__)

    avisar_derivacion(pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "Resumen confidencial de prueba", 1000.0, EnvioFalso())
    avisar_derivacion(pedidos, NUMERO_DUENO, NUMERO_CLIENTE, "Resumen confidencial de prueba", 1010.0, EnvioFalso())

    assert "Aviso de derivación enviado al dueño" in caplog.text
    assert "Aviso de derivación omitido" in caplog.text
    assert NUMERO_CLIENTE not in caplog.text
    assert NUMERO_DUENO not in caplog.text
    assert "2233" in caplog.text
    assert "Resumen confidencial" not in caplog.text
