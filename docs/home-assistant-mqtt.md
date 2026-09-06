# Home Assistant MQTT integration

PrintDirector can publish normalized printer telemetry to an MQTT broker and automatically register each configured printer in Home Assistant through MQTT Discovery.

## Home Assistant prerequisites

1. Configure the Home Assistant MQTT integration and connect it to an MQTT broker (for example the Mosquitto broker add-on).
2. Create broker credentials for PrintDirector if your broker requires authentication.
3. Keep Home Assistant MQTT Discovery enabled (the default in normal Home Assistant MQTT setups).

No Home Assistant YAML entities are required for PrintDirector printers.

## PrintDirector setup

Open **Settings → OBS & network → Home Assistant / MQTT** and configure:

- **Enable MQTT publishing**
- broker host and port
- optional username/password
- state topic prefix (default `printdirector`)
- **Enable Home Assistant MQTT Discovery**
- discovery prefix (default `homeassistant`)

The broker password may also be supplied through `PRINTDIRECTOR_MQTT_PASSWORD` instead of storing it in the local PrintDirector configuration.

Default YAML equivalent:

```yaml
mqtt:
  enabled: true
  host: 192.168.1.50
  port: 1883
  username: printdirector
  password_env: PRINTDIRECTOR_MQTT_PASSWORD
  client_id: printdirector
  topic_prefix: printdirector
  discovery_enabled: true
  discovery_prefix: homeassistant
  qos: 0
  retain: true
  keepalive: 60
  heartbeat_interval: 30
  min_publish_interval: 2
  tls_enabled: false
  tls_insecure: false
```

## Automatic printer lifecycle

The PrintDirector printer ID is the stable Home Assistant device identity.

- Add a printer in PrintDirector → discovery is published and Home Assistant creates the device/entities automatically.
- Rename a printer → the existing device keeps the same identity and its discovery metadata is refreshed.
- Change printer type → the same device identity remains.
- Delete a printer → retained discovery topics and the retained state topic for that printer are cleared.
- Restart Home Assistant → PrintDirector listens for the Home Assistant MQTT birth message and republishes discovery/state.
- Restart or disconnect PrintDirector → MQTT Last Will / explicit shutdown availability marks the PrintDirector-published entities unavailable.

## Topics

Global PrintDirector availability:

```text
printdirector/status
```

Per-printer normalized state:

```text
printdirector/printer/<printer_id>/state
```

Example:

```text
printdirector/printer/fenrir/state
```

State is retained JSON using PrintDirector's normalized `PrinterStatus` model. It includes state, filename, progress, elapsed/remaining time, temperatures and targets, print speed, layers, online/stale flags, and last-update timestamp.

Home Assistant discovery topics use the standard discovery prefix, for example:

```text
homeassistant/sensor/printdirector_fenrir_progress/config
homeassistant/binary_sensor/printdirector_fenrir_online/config
```

## Home Assistant entities

Each printer is grouped as one Home Assistant device and currently exposes:

- State
- Filename
- Progress
- Elapsed Time
- Remaining Time
- Hotend Temperature
- Hotend Target
- Bed Temperature
- Bed Target
- Print Speed
- Current Layer
- Total Layers
- Last Update
- Online
- Telemetry Stale

## Publishing behavior

State changes such as printing/paused/error, filename changes, online/offline, and stale/recovered publish immediately. High-frequency telemetry is rate-limited by `min_publish_interval`, while a retained heartbeat refreshes state every `heartbeat_interval` seconds.

Webhook notifications remain independent of MQTT. A useful split is:

- MQTT for live/continuous state and Home Assistant dashboards.
- Webhooks for discrete notification/automation events.

## TLS

Set `tls_enabled: true` for a TLS broker. Leave `tls_insecure: false` for normal certificate validation. `tls_insecure: true` disables certificate validation and should only be used on a trusted local network when necessary.
