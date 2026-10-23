"""Centralized logging: console in the FastAPI CLI style, full detail in a rotating log file."""

import logging
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings


def setup_logging(log_level: int = logging.INFO) -> None:
    """Send app logs to the same console handlers as uvicorn (styled by `fastapi dev/run`) and to data/logs/backend.log."""
    log_dir = get_settings().paths.logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "backend.log"

    # Reuse the handlers `fastapi dev/run` installed on uvicorn so app logs look like FastAPI's own
    console_handlers = list(logging.getLogger("uvicorn").handlers)
    if not console_handlers:  # plain `uvicorn` without a log config, or a script
        fallback = logging.StreamHandler()
        fallback.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        console_handlers = [fallback]

    # File Handler (10MB max, keep 5 backups) keeps timestamps and logger names for debugging
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Remove existing handlers to prevent duplicate logs on reload
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    for h in [*console_handlers, file_handler]:
        root_logger.addHandler(h)

    # Silence overly verbose external loggers
    for name in ("uvicorn.access", "httpx", "httpcore", "chromadb", "openai", "langgraph"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Writing logs to %s", log_file)
