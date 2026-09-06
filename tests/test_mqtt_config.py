import pytest

from printdirector.config.models import MQTTConfig


def test_mqtt_prefixes_are_normalized():
    cfg = MQTTConfig(topic_prefix="/printdirector/", discovery_prefix="/homeassistant/")
    assert cfg.topic_prefix == "printdirector"
    assert cfg.discovery_prefix == "homeassistant"


def test_mqtt_rejects_wildcard_prefixes():
    with pytest.raises(ValueError):
        MQTTConfig(topic_prefix="printdirector/#")
    with pytest.raises(ValueError):
        MQTTConfig(discovery_prefix="homeassistant/+")


def test_enabled_mqtt_requires_host():
    with pytest.raises(ValueError):
        MQTTConfig(enabled=True, host="   ")
