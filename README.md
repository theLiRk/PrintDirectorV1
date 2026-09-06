# PrintDirector

PrintDirector is a local, asynchronous OBS director for multiple 3D printers. Printer telemetry is the source of truth for print state; OBS owns cameras and video.

## Features
- Multiple Klipper/Moonraker and Bambu Lab LAN-mode printers with reconnect backoff
- Normalized telemetry, stale-data detection, event overrides, deterministic rotation, and manual override
- OBS WebSocket v5 scene and stream control with duplicate-action protection
- Event-driven OBS stream/scene tracking with `GetStreamStatus` polling as a watchdog/fallback
- OBS preflight validation for required scenes, stream service, scene collection, and profile
- Controlled stream recovery for prolonged OBS reconnect states, with optional OBS process restart as a final fallback
- Optional Windows OBS process supervision and automatic launch when OBS is not running
- FastAPI dashboard, transparent per-printer overlays, overview overlay, and live WebSocket updates
- Recent operational event history and generic webhook notifications
- Downloadable redacted diagnostics bundle for troubleshooting
- Rotating persistent logs for unattended troubleshooting
- Liveness/readiness health endpoints
- Demo mode, unit tests, and GitHub Actions CI on Windows and Linux

## Requirements
Python 3.11+, Moonraker and/or supported Bambu Lab LAN-mode printers, and OBS Studio with WebSocket v5 enabled. OBS 28+ includes obs-websocket.

## Install
The project includes setup helpers for first-run installation.

### Quick install

#### macOS/Linux
```bash
chmod +x install.sh
./install.sh
```

#### Windows PowerShell
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./install.ps1
```

This bypass applies only to the current PowerShell session and does not change the machine-wide execution policy. If Windows marked the downloaded script as blocked, run `Unblock-File .\install.ps1` first.

The scripts will:
- create a local `.venv`
- install project dependencies from `requirements.txt`
- create `config.yaml` from `config.example.yaml` if it is missing
- create `.env` from `.env.example` if it is missing
- populate `OBS_WEBSOCKET_PASSWORD` in `.env` when the environment variable is already set

After installation, activate the environment and start the app:

```bash
source .venv/bin/activate
set -a && source .env && set +a
python -m printdirector.main
```

```powershell
.\.venv\Scripts\Activate.ps1
$env:OBS_WEBSOCKET_PASSWORD = "your-password"
python -m printdirector.main
```

Every new PowerShell session must run `.\.venv\Scripts\Activate.ps1` after entering the project directory.

## Configuration
Edit `config.yaml`. Add any number of printers. IDs must be unique and URL-safe. The default dashboard binds to `127.0.0.1`; change this only on a trusted LAN and enable `overlay.allow_lan` intentionally.

OBS camera sources are configured in OBS scenes, not in PrintDirector. Older configs containing `obs.camera_source` remain loadable because unknown legacy keys are ignored, but the field is no longer used or documented.

The dashboard includes a local settings page at `/settings`. Normal operational configuration can be managed there, including printer connections, Director automation, OBS startup/preflight/recovery, stale telemetry monitoring, webhook notifications, and overlay appearance. System settings saved through the UI are stored in a local `*.local.json` override next to the active config file. Overlay appearance is stored in `overlay-settings.json` by default. Generated local config, overlay settings, logs, and `.env` are ignored by Git.

Optional local auth is available for shared LAN scenarios via `auth.enabled` and `auth.token_env` (for example `PRINTDIRECTOR_TOKEN`). When enabled, API and overlay WebSocket access require the configured token except for health endpoints and the local settings/preview pages.

### OBS connection and preflight
`obs.reconnect_interval` controls retry backoff after a lost OBS request/event connection. `obs.status_poll_interval` defaults to 15 seconds. OBS stream and scene events are used as the primary state source; `GetStreamStatus` is retained as a periodic watchdog and as the automatic fallback if the event channel is unavailable.

Preflight is enabled by default. It verifies that OBS is reachable, the required PrintDirector scenes exist, and OBS has a stream service configured before automation treats OBS as ready.

```yaml
obs:
  preflight_enabled: true
  preflight_interval: 30
  startup_ready_timeout: 45
  scene_collection: null
  profile: null
```

`scene_collection` and `profile` are optional. When set, PrintDirector can restore the intended OBS scene collection/profile after reconnect or restart before selecting the correct Director scene. Leave them `null` if you do not need enforcement.

The Settings page includes **Validate OBS**, which runs preflight immediately and reports missing scenes or other readiness problems.

### Automatic OBS startup on Windows
PrintDirector can optionally supervise the local OBS process. When enabled, it checks whether `obs64.exe` is actually running before doing anything. If OBS is already running but the WebSocket is unavailable, PrintDirector waits for the existing OBS instance instead of launching another copy.

```yaml
obs:
  auto_launch: true
  executable: 'C:\Program Files\obs-studio\bin\64bit\obs64.exe'
  launch_args: []
  process_check_interval: 5
  launch_cooldown: 30
```

`executable` is optional. If it is omitted, PrintDirector checks `PATH`, the normal 64-bit OBS install under Program Files, and the common Steam install path. Automatic launch is currently Windows-only and only applies when `obs.host` is local (`127.0.0.1`, `localhost`, or `::1`). Remote OBS targets are never launched locally.

The default `launch_args` is empty, so OBS opens normally. If you prefer OBS minimized for unattended operation, add the desired OBS launch argument in Settings or config.

A relaunch cooldown prevents repeated starts while OBS is still initializing. If Windows process detection fails, PrintDirector deliberately does not launch OBS because avoiding duplicate OBS instances is more important than forcing a restart.

### Stream-health recovery
PrintDirector tracks how long OBS remains in the reconnecting stream state. Recovery is deliberately staged:

1. Wait for the configured reconnect-stuck threshold.
2. Perform one controlled stream stop/start recovery attempt.
3. Enforce a long recovery cooldown so the action cannot loop.
4. Optionally restart the OBS process only if aggressive process recovery is explicitly enabled.
5. Re-run OBS preflight, restore the intended scene/profile/collection, and then allow normal stream automation to resume.

Recommended defaults:

```yaml
obs:
  reconnect_stuck_seconds: 90
  stream_recovery_enabled: true
  stream_recovery_cooldown: 300
  restart_obs_on_stream_failure: false
  restart_obs_cooldown: 600
```

`restart_obs_on_stream_failure` is intentionally **false by default**. Enable it only after normal stream recovery has been proven stable on the production machine. This is a final fallback, not the first recovery action.

### Director automation
The Director can automatically choose scenes and start/stop streaming based on fresh active printer telemetry.

```yaml
director:
  enabled: true
  rotation_interval: 30
  idle_scene: PrintDirector Idle
  overview_scene: Print Farm Overview
  auto_start_stream: false
  auto_stop_stream: false
  stream_stop_delay: 300
  near_complete_threshold: 0.95
```

These controls are also available from **Settings > Operations**. Manual scene commands temporarily disable automatic Director scene selection until **Return to auto** is used.

### Stale telemetry monitoring
A printer can remain technically connected while its telemetry stops changing. PrintDirector therefore tracks freshness separately from the printer's own online/offline flag.

```yaml
monitoring:
  stale_after_seconds: 30
  stale_check_interval: 5
  history_limit: 100
```

When a printer exceeds `stale_after_seconds`, it is marked stale, recorded in event history, and excluded from automatic scene rotation and active-stream decisions until fresh telemetry returns. A stale printer is not automatically paused or cancelled; PrintDirector remains read-only toward printer control.

The dashboard shows fresh/stale printer counts and recent telemetry-state changes.

### Event history and webhook notifications
PrintDirector keeps a bounded recent event history covering printer state changes, telemetry stale/recovery events, OBS availability/recovery, stream recovery, and related operational events. The dashboard shows the recent timeline, and the API exposes it at:

```text
GET /api/events?limit=50
```

Generic JSON webhook notifications are optional:

```yaml
notifications:
  enabled: false
  webhook_url: null
  timeout: 5
  events:
    - printer_error
    - printer_offline
    - print_completed
    - telemetry_stale
    - all_printers_unavailable
    - obs_unavailable
    - obs_restarted
    - stream_recovery_failed
```

Each POST includes `source: "PrintDirector"` plus the event record. The generic format is intended to work with webhook-capable services such as automation platforms, notification gateways, and custom receivers without coupling PrintDirector to one vendor.

Use **Test webhook** in Settings after entering the URL. A failed webhook does not stop PrintDirector; it is logged and normal operation continues.

### Diagnostics bundle
The dashboard includes **Download diagnostics**. The generated ZIP is designed for incident troubleshooting and contains operational state such as:

- effective PrintDirector configuration with secrets redacted
- recent event history
- current printer states and freshness information
- OBS/Director operational status
- platform/package/version information
- recent PrintDirector log data

Passwords, API/auth tokens, Bambu access codes, and similar configured secrets are redacted before the bundle is returned. Diagnostics are available through:

```text
GET /api/diagnostics
```

For an OBS crash or stream-recovery problem, collect this diagnostics bundle together with the matching OBS session log and OBS crash report.

### Logging
Persistent logging is enabled by default:

```yaml
logging:
  level: INFO
  file: logs/printdirector.log
  max_bytes: 10485760
  backup_count: 5
  console: true
```

Relative log paths are resolved next to the active `--config` file. When the file reaches `max_bytes`, it rotates and retains `backup_count` older logs. Set `file: null` to disable file logging. Changing logging settings through the running settings API is persisted but requires a PrintDirector restart so the process handlers can be rebuilt safely.

Moonraker normally listens on port 7125. Find its host address in Mainsail/Fluidd, your router, or the printer host. Verify it locally by opening `http://HOST:7125/printer/info`. If Moonraker authorization restricts your client, allow the PrintDirector host in Moonraker's trusted clients.

## OBS setup
In OBS, open **Tools > WebSocket Server Settings**, enable the server, keep port 4455 unless configured otherwise, and set a password matching `OBS_WEBSOCKET_PASSWORD` or the password stored in PrintDirector's local configuration.

Create the scenes exactly as configured, for example:
- `PrintDirector Idle`
- `Printer - Jötunn`
- `Printer - Fenrir`
- `Print Farm Overview`

Add camera sources manually. PrintDirector never captures or analyzes video. Suggested structure:

```text
Printer - Jötunn
  Jötunn Camera
  Jötunn Overlay (Browser Source)
Printer - Fenrir
  Fenrir Camera
  Fenrir Overlay (Browser Source)
Print Farm Overview
  Camera sources
  Farm Overview (Browser Source)
```

Browser Source URLs:
- Per printer: `http://127.0.0.1:8765/overlay/jotunn`
- Overview: `http://127.0.0.1:8765/overlay/overview`
- Dashboard: `http://127.0.0.1:8765/`

Use a transparent browser-source background and a canvas-sized source for the overview.

## Health monitoring
Two health endpoints are available without authentication:

- `GET /api/health` — process liveness and cached operational status without forcing external connections.
- `GET /api/health/ready` — operational readiness. It performs an OBS watchdog query and, when preflight is enabled, a preflight validation. It returns HTTP 503 when the runtime is not running or OBS is not ready.

Health payloads include OBS connection/stream/preflight state plus printer freshness counts. An individual offline or stale printer does not make the whole PrintDirector process unready, but the condition is visible in the payload and event history.

These endpoints are suitable for local monitoring or a watchdog task.

## Demo and tests
```powershell
.\.venv\Scripts\Activate.ps1
python -m printdirector.main --demo
pytest -q
```

Demo mode uses configured printer names/scenes but does not contact printer hardware. GitHub Actions runs the test suite and Python/JavaScript source syntax checks on both Windows and Linux for pull requests and the configured protected development branches.

## API
Useful read/operations endpoints include:

- `GET /api/health`
- `GET /api/health/ready`
- `GET /api/printers`
- `GET /api/printers/{id}`
- `GET /api/director/status`
- `GET /api/events?limit=50`
- `GET /api/obs/preflight`
- `GET /api/diagnostics`
- `POST /api/notifications/test`
- live updates via `/ws/printers`

Director/stream control endpoints remain available for local automation. If `auth.enabled` is enabled, normal API and WebSocket endpoints require the configured token.

## Windows unattended operation
For long-running use, Task Scheduler is preferable to leaving a PowerShell window open. Create a task that starts at user logon and runs:

- **Program:** `<PrintDirector>\.venv\Scripts\python.exe`
- **Arguments:** `-m printdirector.main --config config.yaml`
- **Start in:** the PrintDirector repository directory

In the task settings, enable **Restart the task if it fails** (for example after 1 minute) and **Run task as soon as possible after a scheduled start is missed**. Because OBS itself normally runs in the interactive desktop session, a user-logon trigger is generally more appropriate than running PrintDirector as a SYSTEM service.

With `obs.auto_launch: true`, a user-logon PrintDirector task can also bring OBS back up if OBS was not running or later exits/crashes. PrintDirector does not terminate OBS when PrintDirector itself shuts down.

If the OBS password exists only as a temporary PowerShell environment variable, Task Scheduler will not inherit it. Use a persistent user environment variable or store the OBS password in PrintDirector's local configuration before relying on unattended startup.

For unattended operation, keep `restart_obs_on_stream_failure` disabled during initial soak testing. Enable it only after confirming normal OBS launch, preflight, scene restoration, stream start/stop, and controlled stream recovery all work correctly on the production host.

## Troubleshooting
- **Dashboard unavailable:** confirm the process is running and port 8765 is free.
- **Printer offline:** verify the Moonraker/Bambu URL, credentials, trusted clients, and host reachability. Reconnection is automatic.
- **Printer shown as stale:** telemetry has stopped updating for longer than `monitoring.stale_after_seconds`. Check the printer connection and PrintDirector log; it will automatically recover when fresh telemetry resumes.
- **OBS offline:** if auto-launch is disabled, start OBS manually. If auto-launch is enabled, check `logs/printdirector.log` for process-detection or executable-path errors. Also verify WebSocket v5 host/port/password and firewall settings.
- **OBS preflight degraded:** run **Validate OBS** in Settings. Check missing scenes, stream service, expected scene collection/profile, and WebSocket connectivity.
- **OBS launches repeatedly:** this should be prevented by process detection and relaunch cooldowns. Stop PrintDirector and collect a diagnostics bundle/log before launching OBS manually.
- **Stream remains reconnecting:** PrintDirector waits for `reconnect_stuck_seconds` before one controlled recovery attempt. Check event history and logs for `stream_recovery_failed` before enabling process restart fallback.
- **OBS event channel unavailable:** PrintDirector logs a warning and automatically falls back to periodic `GetStreamStatus` polling.
- **Scene does not switch:** scene names are case-sensitive and must match configuration exactly.
- **Webhook test fails:** verify the URL accepts an HTTP JSON POST and inspect the PrintDirector log for timeout/HTTP errors.
- **No layer count:** printer telemetry does not always expose it; the UI intentionally hides unavailable values.
- **PowerShell blocks activation:** use `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.
- **Crash investigation:** download the PrintDirector diagnostics bundle and collect the OBS session log/crash report from the same run. Stream-state transitions and OBS connection lifecycle are recorded in the PrintDirector log and recent event history.

## Design notes
A future printer adapter can implement `PrinterAdapter` without changing Director logic. Bambu Lab support is included for LAN-mode printers; computer vision is intentionally not included. PrintDirector does not automatically pause or cancel printers. Temporary loss of one printer, an OBS request connection, or the OBS event channel does not terminate the application.
