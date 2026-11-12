# Configuración de gunicorn (se carga con --config): logging y el arranque del
# reporte semanal. El resto (bind, workers, hilos, socket de control
# desactivado) sigue viniendo de los flags del CMD en el Dockerfile.

# accesslog desactivado: webhook.py ya registra una línea por petición
# (método, ruta sin query string, código de estado) en su propio
# after_request. Tener también el accesslog de gunicorn duplicaba esa línea.
accesslog = None
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):
    # Se ejecuta en cada worker, después del fork: sin esto, los logger.info()
    # de webhook.py y flujo_pedido.py no tienen ningún handler configurado bajo
    # gunicorn (logging.basicConfig solo corría con "python webhook.py" directo,
    # nunca con la fábrica webhook:crear_app() que usa gunicorn) y se perdían
    # en silencio.
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def post_worker_init(worker):
    # Se ejecuta una vez por worker, justo después de cargar la app
    # (webhook:crear_app()): arranca el programador del reporte semanal
    # (sub-fase 5c). Va aquí y no dentro de crear_app para que las pruebas,
    # que crean la app muchas veces, nunca lancen hilos en segundo plano.
    # Con --workers 1 (hoy) hay un solo programador. Si algún día se suben los
    # workers, habría uno por worker, pero el reporte igual sale una sola vez
    # por semana: la reserva en la tabla reportes_enviados es atómica.
    extensiones = getattr(getattr(worker, "wsgi", None), "extensions", {})
    iniciar = extensiones.get("iniciar_reporte_semanal")
    if iniciar is not None:
        iniciar()
