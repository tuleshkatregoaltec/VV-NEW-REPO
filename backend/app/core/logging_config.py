import os
from typing import Any, Dict

os.makedirs("logs", exist_ok=True)

LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "console_colored": {
            "format": "%(levelname)s %(message)s",
            "use_colors": True,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console_colored",
            "level": "INFO",
            "stream": "ext://sys.stdout",
        },
        "file_debug": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "level": "DEBUG",
            "filename": "logs/debug.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 3,
            "encoding": "utf8",
        },
        "file_sql": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "level": "INFO",  # SQLAlchemy logs queries at INFO level
            "filename": "logs/sql.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf8",
        },
    },
    "loggers": {
        # Root Logger (Catch-all)
        "": {
            "handlers": ["console", "file_debug"],
            "level": "INFO",
        },
        # Application Logs (Your code)
        "backend": {
            "handlers": ["console", "file_debug"],
            "level": "DEBUG",  # Allows debug logs in file, but console handler filters to INFO
            "propagate": False,
        },
        # SQLAlchemy Engine (The SQL Queries)
        "sqlalchemy.engine": {
            "handlers": ["file_sql"],  # <--- ONLY to file, not console
            "level": "INFO",
            "propagate": False,  # Stop it from bubbling up to console
        },
        # Redis Cache (Your custom logger)
        "RedisCache": {
            "handlers": ["console", "file_debug"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
