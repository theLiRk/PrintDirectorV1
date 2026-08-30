import pytest

from printdirector.config import AppConfig, load_config
from printdirector.printers.bambu import BambuAdapter


def test_config(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("""printers:
- id: a
  name: A
  moonraker_url: http://x
  obs: {scene: A}
""", encoding="utf-8")
    assert load_config(p).printers[0].id == "a"


def test_bambu_config():
    config = AppConfig.model_validate({
        "printers": [{"id": "a1", "name": "A1", "type": "bambu", "bambu_url": "http://192.168.1.120", "access_code": "12345678", "serial_number": "ABC123456", "obs": {"scene": "A1"}}]
    })
    assert config.printers[0].type == "bambu"


def test_overlay_requires_local_bind_by_default():
    with pytest.raises(ValueError):
        AppConfig.model_validate({
            "printers": [{"id": "a", "name": "A", "moonraker_url": "http://x", "obs": {"scene": "A"}}],
            "overlay": {"host": "0.0.0.0"}
        })


def test_overlay_allows_lan_when_explicitly_enabled():
    config = AppConfig.model_validate({
        "printers": [{"id": "a", "name": "A", "moonraker_url": "http://x", "obs": {"scene": "A"}}],
        "overlay": {"host": "0.0.0.0", "allow_lan": True}
    })
    assert config.overlay.host == "0.0.0.0"


def test_bambu_status_parses_common_payload():
    adapter = BambuAdapter('a1', 'A1', 'http://192.168.1.120')
    adapter._apply_payload({
        'print': {'filename': 'demo.gcode', 'status': 'printing', 'progress': 62, 'time_elapsed': 120, 'remaining_time': 80},
        'nozzle_temp': 210,
        'target_nozzle_temp': 220,
        'bed_temp': 58,
        'target_bed_temp': 60,
    })
    assert adapter.status.state.value == 'printing'
    assert adapter.status.filename == 'demo.gcode'
    assert adapter.status.hotend_temperature == 210
