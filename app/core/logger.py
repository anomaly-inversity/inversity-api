import logging
import sys
import structlog

def setup_logging(pretty: bool = True):
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
    ]

    # Render JSON. Pakai indent=2 agar pretty.
    if pretty:
        processors.append(structlog.processors.JSONRenderer(indent=2))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Konfigurasi standard logging root
    handler = logging.StreamHandler(sys.stdout)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

logger = structlog.get_logger()
