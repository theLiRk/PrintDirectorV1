from pathlib import Path

from printdirector.config.models import PrinterConfig, PrinterOBSConfig


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_TEMPLATE = ROOT / "printdirector" / "overlay" / "templates" / "settings.html"
STREAM_UI = ROOT / "printdirector" / "overlay" / "static" / "stream-exclusion.js"


def test_stream_enabled_defaults_true_for_existing_configs():
    printer = PrinterConfig(
        id="jotunn",
        name="Jötunn",
        type="klipper",
        moonraker_url="http://127.0.0.1:7125",
        obs=PrinterOBSConfig(scene="Printer - Jötunn"),
    )
    assert printer.stream_enabled is True


def test_stream_enabled_can_be_disabled_per_printer():
    printer = PrinterConfig(
        id="draupnir",
        name="Draupnir",
        type="bambu",
        bambu_url="mqtt://192.0.2.10:8883",
        access_code="test-code",
        serial_number="TEST123",
        stream_enabled=False,
        obs=PrinterOBSConfig(scene="Printer - Draupnir"),
    )
    assert printer.stream_enabled is False


def test_settings_loads_stream_exclusion_ui():
    template = SETTINGS_TEMPLATE.read_text(encoding="utf-8")
    source = STREAM_UI.read_text(encoding="utf-8")

    assert "/static/stream-exclusion.js" in template
    assert "printer-stream-enabled" in source
    assert "Include this printer in automatic streaming" in source
    assert "stream_enabled" in source
    assert "MQTT/Home Assistant telemetry" in source
