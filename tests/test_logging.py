import logging

from printdirector.config.models import LoggingConfig
from printdirector.utils.logging import setup_logging


def test_rotating_file_logging_writes_next_to_config(tmp_path):
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    try:
        config = LoggingConfig(
            level="INFO",
            file="logs/printdirector.log",
            max_bytes=2048,
            backup_count=2,
            console=False,
        )
        path = setup_logging(config, tmp_path)
        logging.getLogger("printdirector.test").info("persistent-log-check")
        for handler in root.handlers:
            handler.flush()

        assert path == (tmp_path / "logs" / "printdirector.log").resolve()
        assert path.exists()
        assert "persistent-log-check" in path.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(original_level)
        for handler in original_handlers:
            root.addHandler(handler)
