import json
from types import SimpleNamespace

from printdirector.config.models import MQTTConfig, PrinterConfig
from printdirector.models import PrinterState, PrinterStatus
from printdirector.utils.mqtt import MQTTPublisher


class FakePublishInfo:
    def wait_for_publish(self, timeout=None):
        return True


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakePublishInfo()

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))


def make_publisher():
    cfg = MQTTConfig(
        enabled=True,
        host="mqtt.local",
        topic_prefix="printdirector",
        discovery_prefix="homeassistant",
        min_publish_interval=0,
    )
    printer = PrinterConfig(
        id="fenrir",
        name="Fenrir",
        type="klipper",
        moonraker_url="http://fenrir:7125",
        obs={"scene": "Printer - Fenrir"},
    )
    publisher = MQTTPublisher(cfg, [printer])
    publisher.client = FakeClient()
    publisher.connected = True
    return publisher


def test_home_assistant_discovery_groups_entities_under_stable_printer_device():
    publisher = make_publisher()
    publisher.publish_discovery()

    configs = [item for item in publisher.client.published if item[0].endswith("/config")]
    assert len(configs) == len(publisher.ENTITY_DEFINITIONS)

    state_config = next(item for item in configs if item[0].endswith("printdirector_fenrir_state/config"))
    payload = json.loads(state_config[1])
    assert payload["unique_id"] == "printdirector_fenrir_state"
    assert payload["state_topic"] == "printdirector/printer/fenrir/state"
    assert payload["availability_topic"] == "printdirector/status"
    assert payload["device"]["identifiers"] == ["printdirector_fenrir"]
    assert payload["device"]["name"] == "Fenrir"


def test_normalized_printer_state_is_published_as_retained_json():
    publisher = make_publisher()
    status = PrinterStatus(
        printer_id="fenrir",
        printer_name="Fenrir",
        state=PrinterState.PRINTING,
        filename="part.gcode",
        progress=0.625,
        estimated_remaining=900,
        hotend_temperature=220.5,
        hotend_target=220,
        bed_temperature=60,
        bed_target=60,
        current_layer=25,
        total_layers=40,
        online=True,
    )

    assert publisher.publish_status(status, force=True) is True
    topic, raw, qos, retain = publisher.client.published[-1]
    payload = json.loads(raw)
    assert topic == "printdirector/printer/fenrir/state"
    assert retain is True
    assert payload["state"] == "printing"
    assert payload["progress"] == 0.625
    assert payload["current_layer"] == 25
    assert payload["online"] is True


def test_home_assistant_birth_republishes_discovery_and_latest_state():
    publisher = make_publisher()
    status = PrinterStatus(
        printer_id="fenrir",
        printer_name="Fenrir",
        state=PrinterState.PRINTING,
        progress=0.5,
        online=True,
    )
    publisher.publish_status(status, force=True)
    publisher.client.published.clear()

    publisher._on_message(
        publisher.client,
        None,
        SimpleNamespace(topic="homeassistant/status", payload=b"online"),
    )

    topics = [item[0] for item in publisher.client.published]
    assert "homeassistant/sensor/printdirector_fenrir_state/config" in topics
    assert "printdirector/printer/fenrir/state" in topics


def test_removed_printer_discovery_is_cleared_with_retained_empty_payloads():
    publisher = make_publisher()
    assert publisher.clear_discovery({"fenrir"}) is True

    discovery = [item for item in publisher.client.published if item[0].endswith("/config")]
    assert discovery
    assert all(item[1] == "" and item[3] is True for item in discovery)
    assert publisher.client.published[-1][0] == "printdirector/printer/fenrir/state"
    assert publisher.client.published[-1][1] == ""


def test_mqtt_config_defaults_are_home_assistant_ready():
    cfg = MQTTConfig()
    assert cfg.discovery_enabled is True
    assert cfg.discovery_prefix == "homeassistant"
    assert cfg.topic_prefix == "printdirector"
    assert cfg.password_env == "PRINTDIRECTOR_MQTT_PASSWORD"
