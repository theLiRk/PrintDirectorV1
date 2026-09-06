import io
import json
import platform
import sys
import zipfile
from importlib import metadata
from pathlib import Path


SECRET_KEYS = {"password", "token", "access_code", "secret", "api_key"}


def redact(value, key=None):
    if key and key.lower() in SECRET_KEYS:
        return "***REDACTED***" if value else value
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _json_bytes(value):
    return json.dumps(value, indent=2, default=str, ensure_ascii=False).encode("utf-8")


def _package_versions():
    names = ["obsws-python", "fastapi", "uvicorn", "aiohttp", "paho-mqtt", "pydantic"]
    versions = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _read_log_tail(runtime, max_bytes=2 * 1024 * 1024):
    file_name = runtime.config.logging.file
    if not file_name:
        return None
    path = Path(file_name)
    if not path.is_absolute():
        path = runtime.config_path.parent / path
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read()
    except OSError:
        return None


def build_diagnostics_zip(runtime):
    buffer = io.BytesIO()
    config = redact(runtime.config.model_dump(mode="json"))
    status = runtime.operational_status()
    printers = [item.model_dump(mode="json") for item in runtime.manager.statuses().values()]
    versions = {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": _package_versions(),
    }

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("effective-config-redacted.json", _json_bytes(config))
        archive.writestr("operational-status.json", _json_bytes(status))
        archive.writestr("printers.json", _json_bytes(printers))
        archive.writestr("events.json", _json_bytes(runtime.history.list()))
        archive.writestr("versions.json", _json_bytes(versions))
        log_tail = _read_log_tail(runtime)
        if log_tail:
            archive.writestr("printdirector-log-tail.txt", log_tail)
    return buffer.getvalue()
