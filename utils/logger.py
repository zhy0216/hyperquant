import logging
import logging.handlers
from pathlib import Path

import structlog


def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/hyperquant.log",
    max_size_mb: int = 50,
    backup_count: int = 5,
) -> None:
    """Configure structlog with a RotatingFileHandler and console output.

    Call once at application startup before any logging takes place.

    Args:
        level: Root log level string, e.g. "INFO" or "DEBUG".
        log_file: Path to the rotating log file.
        max_size_mb: Maximum size of a single log file in megabytes.
        backup_count: Number of rotated backup files to keep.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Ensure the log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Shared processors for structlog
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
