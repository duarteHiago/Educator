import logging
import structlog
from pathlib import Path


def configure_logging(
    log_level: str = "DEBUG",
    log_file: Path | None = None,
    silent_console: bool = False,
) -> None:
    """
    silent_console=True: logs vão só para o arquivo — sem poluir o terminal.
    Usado no .exe distribuído; em dev, console permanece ativo.
    """
    log_file = log_file or Path("./logs/educator.jsonl")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.DEBUG)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(file_formatter)

    root_logger = logging.getLogger()
    # Limpa handlers anteriores para evitar duplicação em múltiplas chamadas
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)

    if not silent_console:
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(),
            foreign_pre_chain=shared_processors,
        )
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
