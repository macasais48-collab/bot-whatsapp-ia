# Configuración de logging de gunicorn (se carga con --config). El resto
# (bind, workers, hilos, socket de control desactivado) sigue viniendo de los
# flags del CMD en el Dockerfile; aquí no se toca.

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
