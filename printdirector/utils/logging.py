import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(config="INFO", base_dir=None):
    """Configure console and optional rotating file logging.

    ``config`` may be a LoggingConfig instance or a level string for backwards
    compatibility. Relative log paths are resolved next to the active config file.
    Returns the resolved log path, or ``None`` when file logging is disabled.
    """
    if isinstance(config, str):
        level_name = config
        file_name = None
        max_bytes = 10 * 1024 * 1024
        backup_count = 5
        console = True
    else:
        level_name = config.level
        file_name = config.file
        max_bytes = config.max_bytes
        backup_count = config.backup_count
        console = config.console

    level = getattr(logging, str(level_name).upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    log_path = None
    if file_name:
        log_path = Path(file_name)
        if not log_path.is_absolute():
            log_path = Path(base_dir or Path.cwd()) / log_path
        log_path = log_path.resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return log_path
