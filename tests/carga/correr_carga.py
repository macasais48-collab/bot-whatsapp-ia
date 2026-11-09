"""Prueba de carga de BotWhatsApp: simula varios clientes distintos haciendo un
pedido completo al mismo tiempo contra el webhook, SIN llamar nunca a Meta ni a
Anthropic de verdad (ver servidor_prueba.py) y sin tocar la base de datos del
volumen de producción (todo vive en un directorio temporal).

Uso:
    ./venv/Scripts/python.exe tests/carga/correr_carga.py --clientes 20
    ./venv/Scripts/python.exe tests/carga/correr_carga.py --clientes 50 --hilos 12

Queda fuera de la suite normal de pytest a propósito (no sigue el patrón
test_*.py ni se importa desde ningún test).
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import statistics
import sys
import tempfile
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from escenario_cliente import construir_pasos, total_esperado  # noqa: E402
from firmar import firmar  # noqa: E402
from servidor_prueba import SECRETO_PRUEBA, Registrador, ServidorDePrueba, construir_app  # noqa: E402

from pedidos import ESTADO_RECIBIDO, Pedidos  # noqa: E402

RUTA_RESULTADOS = Path(__file__).resolve().parent / "resultados"


def _numero_ficticio(indice: int) -> str:
    # Rango claramente ficticio (57300000xxxx), nunca un número real.
    return f"5730000{indice:05d}"


def _ejecutar_cliente(numero: str, indice: int, puerto: int) -> dict:
    url = f"http://127.0.0.1:{puerto}/webhook"
    pasos_resultado = []
    inicio_pedido = time.time()
    for nombre_paso, construir_payload in construir_pasos(numero, indice):
        payload = construir_payload()
        cuerpo = json.dumps(payload).encode("utf-8")
        encabezados = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": firmar(cuerpo, SECRETO_PRUEBA),
        }
        inicio = time.time()
        error = None
        codigo = None
        try:
            respuesta = requests.post(url, data=cuerpo, headers=encabezados, timeout=30)
            codigo = respuesta.status_code
        except requests.exceptions.RequestException as exc:
            error = type(exc).__name__
        duracion = time.time() - inicio
        pasos_resultado.append(
            {"paso": nombre_paso, "duracion_s": duracion, "codigo": codigo, "error": error}
        )
    duracion_total = time.time() - inicio_pedido
    return {"numero": numero, "indice": indice, "pasos": pasos_resultado, "duracion_total_s": duracion_total}


def _resumir_tiempos(valores: list[float]) -> dict:
    if not valores:
        return {"promedio_s": None, "maximo_s": None, "n": 0}
    return {"promedio_s": round(statistics.mean(valores), 3), "maximo_s": round(max(valores), 3), "n": len(valores)}


def correr(clientes: int, hilos: int, puerto: int, retraso_meta: float, retraso_ia: float) -> dict:
    tmp_dir = Path(tempfile.mkdtemp(prefix="botwhatsapp_carga_"))
    try:
        registrador = Registrador()
        app = construir_app(
            ruta_bd_pedidos=tmp_dir / "pedidos.db",
            ruta_bd_historial=tmp_dir / "historial.db",
            registrador=registrador,
            retraso_meta=retraso_meta,
            retraso_ia=retraso_ia,
        )
        servidor = ServidorDePrueba(app, puerto=puerto, hilos=hilos)
        servidor.iniciar()
        try:
            numeros = [_numero_ficticio(i) for i in range(clientes)]
            inicio_total = time.time()
            with ThreadPoolExecutor(max_workers=clientes) as pool:
                futuros = [pool.submit(_ejecutar_cliente, numero, i, puerto) for i, numero in enumerate(numeros)]
                resultados_clientes = [f.result() for f in as_completed(futuros)]
            duracion_pared = time.time() - inicio_total
        finally:
            servidor.detener()

        # --- Verificación: ningún pedido mezclado, cada cliente recibió solo lo suyo ---
        pedidos = Pedidos(tmp_dir / "pedidos.db")
        pedidos_recibidos = {p["numero_cliente"]: p for p in pedidos.listar_por_estados([ESTADO_RECIBIDO])}

        pedidos_completos = 0
        pedidos_mezclados = 0
        for numero, indice in zip(numeros, range(clientes)):
            pedido = pedidos_recibidos.get(numero)
            if pedido is None:
                continue
            total_ok = pedido["total"] == total_esperado(indice)
            metodo_ok = pedido["metodo_pago"] == "efectivo"
            numero_ok = pedido["numero_cliente"] == numero
            if total_ok and metodo_ok and numero_ok:
                pedidos_completos += 1
            else:
                pedidos_mezclados += 1

        envios_por_numero_distintos = registrador.numeros_distintos()
        numeros_inesperados = envios_por_numero_distintos - set(numeros)
        if numeros_inesperados:
            pedidos_mezclados += len(numeros_inesperados)

        total_envios_esperados = clientes * 6  # 6 pasos -> 6 envíos, ver escenario_cliente.py
        total_envios_reales = len(registrador.todos())
        mensajes_perdidos = max(0, total_envios_esperados - total_envios_reales)

        errores_http = sum(
            1
            for r in resultados_clientes
            for p in r["pasos"]
            if p["error"] is not None or (p["codigo"] is not None and p["codigo"] != 200)
        )

        tiempos_por_paso: dict[str, list[float]] = {}
        for r in resultados_clientes:
            for p in r["pasos"]:
                tiempos_por_paso.setdefault(p["paso"], []).append(p["duracion_s"])

        resultado = {
            "config": {
                "clientes": clientes,
                "hilos": hilos,
                "retraso_meta_s": retraso_meta,
                "retraso_ia_s": retraso_ia,
            },
            "duracion_pared_s": round(duracion_pared, 3),
            "tiempos_por_paso": {paso: _resumir_tiempos(v) for paso, v in tiempos_por_paso.items()},
            "tiempo_total_por_pedido": _resumir_tiempos([r["duracion_total_s"] for r in resultados_clientes]),
            "pedidos_completos": pedidos_completos,
            "pedidos_mezclados": pedidos_mezclados,
            "errores_http": errores_http,
            "mensajes_perdidos": mensajes_perdidos,
        }
        return resultado
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _imprimir_resumen(resultado: dict) -> None:
    cfg = resultado["config"]
    print(f"\n=== Prueba de carga: {cfg['clientes']} clientes, {cfg['hilos']} hilos ===")
    print(f"Duración total (pared): {resultado['duracion_pared_s']} s")
    print(f"Pedidos completos correctos: {resultado['pedidos_completos']} / {cfg['clientes']}")
    print(f"Pedidos mezclados: {resultado['pedidos_mezclados']}")
    print(f"Errores HTTP: {resultado['errores_http']}")
    print(f"Mensajes perdidos: {resultado['mensajes_perdidos']}")
    print("Tiempos por paso (promedio / máximo, segundos):")
    for paso, t in resultado["tiempos_por_paso"].items():
        print(f"  - {paso}: {t['promedio_s']} / {t['maximo_s']} (n={t['n']})")
    t_total = resultado["tiempo_total_por_pedido"]
    print(f"Tiempo total por pedido (promedio / máximo): {t_total['promedio_s']} / {t_total['maximo_s']} s")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prueba de carga de BotWhatsApp (sin red real).")
    parser.add_argument("--clientes", type=int, default=20)
    parser.add_argument("--hilos", type=int, default=12, help="Debe igualar --threads de gunicorn en producción.")
    parser.add_argument("--puerto", type=int, default=8899)
    parser.add_argument("--retraso-meta", type=float, default=0.2, help="Segundos que imitan la latencia de Graph API.")
    parser.add_argument("--retraso-ia", type=float, default=1.5, help="Segundos que imitan la latencia de Claude.")
    parser.add_argument("--etiqueta", default=None, help="Nombre con el que se guarda el resultado (p. ej. 'linea_base').")
    args = parser.parse_args(argv)

    resultado = correr(args.clientes, args.hilos, args.puerto, args.retraso_meta, args.retraso_ia)
    _imprimir_resumen(resultado)

    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    etiqueta = args.etiqueta or f"carga_{args.clientes}c_{args.hilos}h_{int(time.time())}"
    ruta_salida = RUTA_RESULTADOS / f"{etiqueta}.json"
    ruta_salida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultado guardado en: {ruta_salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
