import asyncio
import json
import logging
import os
import ssl
import threading
from time import monotonic

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


class MQTTPublisher:
    """Publish normalized PrintDirector state and Home Assistant discovery data."""

    ENTITY_DEFINITIONS = (
        {"component": "sensor", "key": "state", "name": "State", "icon": "mdi:printer-3d", "template": "{{ value_json.state }}"},
        {"component": "sensor", "key": "filename", "name": "Filename", "icon": "mdi:file-outline", "template": "{{ value_json.filename or '' }}"},
        {"component": "sensor", "key": "progress", "name": "Progress", "icon": "mdi:progress-clock", "template": "{{ (value_json.progress * 100) | round(1) }}", "unit": "%", "state_class": "measurement"},
        {"component": "sensor", "key": "elapsed_time", "name": "Elapsed Time", "icon": "mdi:timer-outline", "template": "{{ value_json.elapsed_time }}", "unit": "s", "device_class": "duration", "state_class": "measurement"},
        {"component": "sensor", "key": "estimated_remaining", "name": "Remaining Time", "icon": "mdi:timer-sand", "template": "{{ value_json.estimated_remaining }}", "unit": "s", "device_class": "duration", "state_class": "measurement"},
        {"component": "sensor", "key": "hotend_temperature", "name": "Hotend Temperature", "icon": "mdi:thermometer", "template": "{{ value_json.hotend_temperature }}", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
        {"component": "sensor", "key": "hotend_target", "name": "Hotend Target", "icon": "mdi:thermometer-chevron-up", "template": "{{ value_json.hotend_target }}", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
        {"component": "sensor", "key": "bed_temperature", "name": "Bed Temperature", "icon": "mdi:radiator", "template": "{{ value_json.bed_temperature }}", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
        {"component": "sensor", "key": "bed_target", "name": "Bed Target", "icon": "mdi:radiator", "template": "{{ value_json.bed_target }}", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
        {"component": "sensor", "key": "print_speed", "name": "Print Speed", "icon": "mdi:speedometer", "template": "{{ value_json.print_speed }}", "unit": "%", "state_class": "measurement"},
        {"component": "sensor", "key": "current_layer", "name": "Current Layer", "icon": "mdi:layers-outline", "template": "{{ value_json.current_layer }}", "state_class": "measurement"},
        {"component": "sensor", "key": "total_layers", "name": "Total Layers", "icon": "mdi:layers-triple-outline", "template": "{{ value_json.total_layers }}", "state_class": "measurement"},
        {"component": "sensor", "key": "last_update", "name": "Last Update", "icon": "mdi:clock-outline", "template": "{{ value_json.last_update }}", "device_class": "timestamp"},
        {"component": "binary_sensor", "key": "online", "name": "Online", "icon": "mdi:lan-connect", "template": "{{ 'ON' if value_json.online else 'OFF' }}", "payload_on": "ON", "payload_off": "OFF"},
        {"component": "binary_sensor", "key": "stale", "name": "Telemetry Stale", "icon": "mdi:clock-alert-outline", "template": "{{ 'ON' if value_json.stale else 'OFF' }}", "payload_on": "ON", "payload_off": "OFF", "device_class": "problem"},
    )

    def __init__(self, config, printer_configs):
        self.config = config
        self.printers = {printer.id: printer for printer in printer_configs}
        self.client = None
        self.connected = False
        self._latest = {}
        self._last_payload = {}
        self._last_publish_at = {}
        self._heartbeat_task = None
        self._lock = threading.RLock()

    @property
    def enabled(self):
        return bool(self.config.enabled)

    @property
    def topic_prefix(self):
        return self.config.topic_prefix.strip().strip("/")

    @property
    def discovery_prefix(self):
        return self.config.discovery_prefix.strip().strip("/")

    @property
    def availability_topic(self):
        return f"{self.topic_prefix}/status"

    def state_topic(self, printer_id):
        return f"{self.topic_prefix}/printer/{printer_id}/state"

    def discovery_topic(self, printer_id, definition):
        object_id = f"printdirector_{printer_id}_{definition['key']}"
        return f"{self.discovery_prefix}/{definition['component']}/{object_id}/config"

    def _device(self, printer):
        printer_type = getattr(printer, "type", "printer")
        model = "Bambu Lab printer" if printer_type == "bambu" else "Klipper printer"
        return {
            "identifiers": [f"printdirector_{printer.id}"],
            "name": printer.name,
            "manufacturer": "PrintDirector",
            "model": model,
        }

    def discovery_payload(self, printer, definition):
        unique_id = f"printdirector_{printer.id}_{definition['key']}"
        payload = {
            "name": definition["name"],
            "unique_id": unique_id,
            "state_topic": self.state_topic(printer.id),
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "value_template": definition["template"],
            "device": self._device(printer),
        }
        if definition.get("icon"):
            payload["icon"] = definition["icon"]
        if definition.get("unit"):
            payload["unit_of_measurement"] = definition["unit"]
        if definition.get("device_class"):
            payload["device_class"] = definition["device_class"]
        if definition.get("state_class"):
            payload["state_class"] = definition["state_class"]
        if definition.get("payload_on"):
            payload["payload_on"] = definition["payload_on"]
        if definition.get("payload_off"):
            payload["payload_off"] = definition["payload_off"]
        return payload

    def _publish(self, topic, payload, retain=None):
        client = self.client
        if client is None or not self.connected:
            return False
        if not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        try:
            client.publish(
                topic,
                payload,
                qos=self.config.qos,
                retain=self.config.retain if retain is None else retain,
            )
            return True
        except Exception as exc:
            log.warning("MQTT publish failed for %s: %s", topic, exc)
            return False

    def publish_discovery(self, printer_ids=None):
        if not self.config.discovery_enabled or not self.connected:
            return
        wanted = set(printer_ids or self.printers)
        for printer_id, printer in self.printers.items():
            if printer_id not in wanted:
                continue
            for definition in self.ENTITY_DEFINITIONS:
                self._publish(
                    self.discovery_topic(printer_id, definition),
                    self.discovery_payload(printer, definition),
                    retain=True,
                )

    def clear_discovery(self, printer_ids=None):
        if not self.config.discovery_enabled or not self.connected:
            return False
        wanted = set(printer_ids or self.printers)
        for printer_id in wanted:
            for definition in self.ENTITY_DEFINITIONS:
                self._publish(self.discovery_topic(printer_id, definition), "", retain=True)
            self._publish(self.state_topic(printer_id), "", retain=True)
        return True

    def _status_payload(self, status):
        return status.model_dump(mode="json")

    @staticmethod
    def _materially_changed(previous, current):
        if previous is None:
            return True
        for key in ("state", "filename", "online", "stale", "current_layer", "total_layers"):
            if previous.get(key) != current.get(key):
                return True
        thresholds = {
            "progress": 0.005,
            "elapsed_time": 10,
            "estimated_remaining": 10,
            "hotend_temperature": 0.5,
            "hotend_target": 0.5,
            "bed_temperature": 0.5,
            "bed_target": 0.5,
            "print_speed": 1.0,
        }
        for key, threshold in thresholds.items():
            old, new = previous.get(key), current.get(key)
            if (old is None) != (new is None):
                return True
            if old is not None and new is not None and abs(float(new) - float(old)) >= threshold:
                return True
        return False

    def publish_status(self, status, force=False):
        payload = self._status_payload(status)
        printer_id = status.printer_id
        with self._lock:
            self._latest[printer_id] = status.model_copy(deep=True)
            previous = self._last_payload.get(printer_id)
            last_at = self._last_publish_at.get(printer_id, 0.0)
            now = monotonic()
            changed = self._materially_changed(previous, payload)
            due = now - last_at >= self.config.min_publish_interval
            if not force and (not changed or not due):
                return False
            if not self._publish(self.state_topic(printer_id), payload, retain=True):
                return False
            self._last_payload[printer_id] = payload
            self._last_publish_at[printer_id] = now
            return True

    def publish_all_states(self, force=True):
        with self._lock:
            statuses = list(self._latest.values())
        for status in statuses:
            self.publish_status(status, force=force)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            self.connected = False
            log.warning("MQTT broker connection refused: %s", reason_code)
            return
        self.connected = True
        log.info("MQTT broker connected at %s:%s", self.config.host, self.config.port)
        client.subscribe(f"{self.discovery_prefix}/status", qos=self.config.qos)
        self._publish(self.availability_topic, "online", retain=True)
        self.publish_discovery()
        self.publish_all_states(force=True)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        self.connected = False
        if reason_code != 0:
            log.warning("MQTT broker connection lost: %s", reason_code)

    def _on_message(self, client, userdata, message):
        if message.topic != f"{self.discovery_prefix}/status":
            return
        try:
            payload = message.payload.decode("utf-8").strip().lower()
        except UnicodeDecodeError:
            return
        if payload == "online":
            log.info("Home Assistant MQTT birth received; republishing discovery")
            self.publish_discovery()
            self.publish_all_states(force=True)

    async def start(self):
        if not self.enabled or self.client is not None:
            return
        password = self.config.password or os.getenv(self.config.password_env, "")
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.config.client_id,
        )
        if self.config.username:
            client.username_pw_set(self.config.username, password or None)
        if self.config.tls_enabled:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            if self.config.tls_insecure:
                client.tls_insecure_set(True)
        client.will_set(
            self.availability_topic,
            payload="offline",
            qos=self.config.qos,
            retain=True,
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self.client = client
        try:
            client.connect_async(self.config.host, self.config.port, self.config.keepalive)
            client.loop_start()
        except Exception:
            self.client = None
            raise
        self._heartbeat_task = asyncio.create_task(self._heartbeat(), name="mqtt-heartbeat")

    async def _heartbeat(self):
        while True:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                self.publish_all_states(force=True)
                if self.connected:
                    self._publish(self.availability_topic, "online", retain=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MQTT heartbeat failed")

    async def stop(self):
        task, self._heartbeat_task = self._heartbeat_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        client, self.client = self.client, None
        if client is None:
            self.connected = False
            return
        if self.connected:
            try:
                info = client.publish(
                    self.availability_topic,
                    "offline",
                    qos=self.config.qos,
                    retain=True,
                )
                await asyncio.to_thread(info.wait_for_publish, 2)
            except Exception as exc:
                log.debug("Unable to publish MQTT shutdown state: %s", exc)
        try:
            await asyncio.to_thread(client.disconnect)
        except Exception as exc:
            log.debug("MQTT disconnect failed: %s", exc)
        try:
            await asyncio.to_thread(client.loop_stop)
        except Exception as exc:
            log.debug("MQTT loop stop failed: %s", exc)
        self.connected = False
