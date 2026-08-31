import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from printdirector.models import PrinterState
from .base import PrinterAdapter

log = logging.getLogger(__name__)


class BambuAdapter(PrinterAdapter):
  def __init__(self, printer_id: str, printer_name: str, url: str,
               access_code: Optional[str] = None,
               serial_number: Optional[str] = None):
    super().__init__(printer_id, printer_name)
    self.url = str(url).rstrip('/')
    self.access_code = (access_code or '').strip()
    self.serial_number = (serial_number or '').strip()
    self._stop = None
    self._mqtt = None
    self._messages = None
    self._loop = None
    self._latest_payload = {}

  def _ensure_stop_event(self):
    if self._stop is None:
      self._stop = asyncio.Event()
    return self._stop

  def _mqtt_host_port(self):
    parsed = urlparse(self.url if '://' in self.url else f'mqtt://{self.url}')
    return parsed.hostname or parsed.path, parsed.port or 8883

  def _on_connect(self, client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
      self._loop.call_soon_threadsafe(
        self._messages.put_nowait,
        ConnectionError(f'Bambu MQTT connection refused: {reason_code}'),
      )
      return
    report_topic = f'device/{self.serial_number}/report'
    client.subscribe(report_topic, qos=0)
    client.publish(
      f'device/{self.serial_number}/request',
      json.dumps({'pushing': {'sequence_id': '0', 'command': 'pushall'}}),
      qos=0,
    )

  def _on_message(self, client, userdata, message):
    try:
      payload = json.loads(message.payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
      log.debug('%s sent invalid MQTT data: %s', self.printer_name, exc)
      return
    self._loop.call_soon_threadsafe(self._messages.put_nowait, payload)

  def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
    if reason_code != 0 and self._loop is not None and self._messages is not None:
      self._loop.call_soon_threadsafe(
        self._messages.put_nowait,
        ConnectionError(f'Bambu MQTT connection lost: {reason_code}'),
      )

  def _connect(self):
    host, port = self._mqtt_host_port()
    if not host:
      raise ConnectionError('Bambu printer host is missing')
    if not self.access_code or not self.serial_number:
      raise ConnectionError('Bambu access code and serial number are required')
    messages = asyncio.Queue()
    self._messages = messages
    self._loop = asyncio.get_running_loop()
    client = mqtt.Client(
      mqtt.CallbackAPIVersion.VERSION2,
      client_id=f'printdirector-{self.printer_id}',
    )
    client.username_pw_set('bblp', self.access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = self._on_connect
    client.on_message = self._on_message
    client.on_disconnect = self._on_disconnect
    client.connect(host, port, keepalive=60)
    client.loop_start()
    self._mqtt = client
    return client, messages

  async def _disconnect(self):
    client, self._mqtt = self._mqtt, None
    if client is not None:
      client.loop_stop()
      client.disconnect()
    self._messages = None
    self._loop = None
    self._latest_payload = {}

  async def stop(self):
    self._ensure_stop_event().set()
    await self._disconnect()

  async def run(self):
    stop = self._ensure_stop_event()
    delay = 2
    while not stop.is_set():
      try:
        client, messages = self._connect()
        delay = 2
        while not stop.is_set():
          payload = await asyncio.wait_for(messages.get(), timeout=30)
          if isinstance(payload, Exception):
            raise payload
          self._apply_payload(payload)
      except asyncio.CancelledError:
        raise
      except Exception as exc:
        log.warning('%s connection lost: %s', self.printer_name, exc)
        self.status.online = False
        self.status.state = PrinterState.OFFLINE
        self.publish()
      finally:
        await self._disconnect()
      try:
        await asyncio.wait_for(stop.wait(), delay)
      except asyncio.TimeoutError:
        pass
      delay = min(delay * 2, 30)

  def _lookup(self, node: Any, keys):
    stack = [node]
    seen = set()
    while stack:
      current = stack.pop()
      if id(current) in seen:
        continue
      seen.add(id(current))
      if isinstance(current, dict):
        for key in keys:
          if key in current:
            return current[key]
        stack.extend(value for value in current.values()
                     if isinstance(value, (dict, list)))
      elif isinstance(current, list):
        stack.extend(item for item in current
                     if isinstance(item, (dict, list)))
    return None

  def _pick_number(self, payload: Any, keys, default=None):
    value = self._lookup(payload, keys)
    try:
      return default if value is None else float(value)
    except (TypeError, ValueError):
      return default

  def _pick_int(self, payload: Any, keys, default=None):
    value = self._pick_number(payload, keys, default)
    return None if value is None else int(value)

  def _apply_payload(self, payload: dict):
    self._merge_payload(self._latest_payload, payload)
    state_payload = self._latest_payload
    if isinstance(state_payload.get('msg'), dict):
      state_payload = state_payload['msg']
    if isinstance(state_payload.get('print'), dict):
      state_payload = {**state_payload, **state_payload['print']}

    state_name = str(self._lookup(
      state_payload,
      ['gcode_state', 'state', 'status', 'machine_status', 'print_status'],
    ) or 'idle').lower()
    states = {
      'printing': PrinterState.PRINTING,
      'running': PrinterState.PRINTING,
      'paused': PrinterState.PAUSED,
      'pause': PrinterState.PAUSED,
      'finish': PrinterState.COMPLETE,
      'complete': PrinterState.COMPLETE,
      'failed': PrinterState.ERROR,
      'error': PrinterState.ERROR,
    }
    progress = self._pick_number(
      state_payload, ['mc_percent', 'progress', 'completion', 'percent']
    ) or 0
    if progress > 1:
      progress /= 100
    elapsed = self._pick_number(
      state_payload, ['mc_print_time', 'print_time', 'elapsed_time']
    ) or 0
    remaining = self._pick_number(
      state_payload, ['mc_remaining_time', 'remaining_time', 'time_remaining']
    )
    filename = self._lookup(
      state_payload, ['gcode_file', 'filename', 'file_name', 'job_name']
    )
    self.status = self.status.model_copy(update={
      'state': states.get(state_name, PrinterState.IDLE),
      'filename': str(filename) if filename is not None else None,
      'progress': max(0.0, min(1.0, progress)),
      'elapsed_time': float(elapsed),
      'estimated_remaining': None if remaining is None else max(0.0, remaining),
      'hotend_temperature': self._pick_number(
        state_payload, ['nozzle_temper', 'nozzle_temp', 'hotend_temperature']
      ),
      'hotend_target': self._pick_number(
        state_payload, ['nozzle_target_temper', 'nozzle_target']
      ),
      'bed_temperature': self._pick_number(
        state_payload, ['bed_temper', 'bed_temp', 'bed_temperature']
      ),
      'bed_target': self._pick_number(
        state_payload, ['bed_target_temper', 'bed_target']
      ),
      'current_layer': self._pick_int(
        state_payload, ['layer_num', 'current_layer']
      ),
      'total_layers': self._pick_int(
        state_payload, ['total_layer_num', 'total_layers']
      ),
      'online': True,
      'last_update': datetime.now(timezone.utc),
    })
    self.publish()

  def _merge_payload(self, target: dict, update: dict) -> None:
    for key, value in update.items():
     if isinstance(value, dict) and isinstance(target.get(key), dict):
       self._merge_payload(target[key], value)
     else:
       target[key] = value
