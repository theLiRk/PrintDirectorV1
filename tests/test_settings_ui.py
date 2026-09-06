from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "printdirector" / "overlay" / "templates" / "settings.html"
PRINTER_JS = ROOT / "printdirector" / "overlay" / "static" / "printer-editor.js"
GLOBAL_JS = ROOT / "printdirector" / "overlay" / "static" / "settings-global.js"


class SettingsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])


def test_settings_page_has_single_printer_workspace_contract():
    parser = SettingsParser()
    parser.feed(TEMPLATE.read_text(encoding="utf-8"))

    assert len(parser.ids) == len(set(parser.ids)), "Settings page contains duplicate element IDs"
    ids = set(parser.ids)
    required = {
        "printer-list",
        "printer-editor",
        "add-printer",
        "save-printer",
        "discard-printer-changes",
        "delete-printer",
        "printer-name",
        "printer-type",
        "printer-id",
        "printer-scene",
        "printer-custom-overlay",
        "printer-preview-card",
    }
    assert required <= ids

    assert "printer-top-select" not in ids
    assert "printer-override-select" not in ids
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "/static/settings-global.js" in template
    assert "/static/printer-editor.js" in template


def test_printer_switch_preserves_draft_before_selection_changes():
    source = PRINTER_JS.read_text(encoding="utf-8")
    switch_start = source.index("function switchPrinter(key)")
    switch_end = source.index("function uniqueNewPrinterId", switch_start)
    switch_source = source[switch_start:switch_end]

    assert "captureActiveDraft(false);" in switch_source
    assert switch_source.index("captureActiveDraft(false);") < switch_source.index("activeDraftKey = key;")
    assert "printerDrafts = new Map()" in source
    assert "beforeunload" in source


def test_save_printer_persists_connection_and_overlay_behind_one_action():
    source = PRINTER_JS.read_text(encoding="utf-8")
    save_start = source.index("async function savePrinterDraft()")
    save_end = source.index("function discardPrinterDraft", save_start)
    save_source = source[save_start:save_end]

    assert "'/api/system-config'" in save_source
    assert "'/api/settings'" in save_source
    assert "printer_overrides" in save_source


def test_connections_workspace_exposes_home_assistant_mqtt_configuration():
    source = GLOBAL_JS.read_text(encoding="utf-8")
    assert "Home Assistant / MQTT" in source
    assert "mqtt-enabled" in source
    assert "mqtt-host" in source
    assert "mqtt-discovery-enabled" in source
    assert "mqtt-discovery-prefix" in source
    assert "PRINTDIRECTOR_MQTT_PASSWORD" in source
    save_start = source.index("async function saveConnections()")
    save_end = source.index("async function refreshPrinterStatuses", save_start)
    assert "mqtt:" in source[save_start:save_end]
