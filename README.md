# PrintDirector

PrintDirector is a local, asynchronous OBS director for multiple 3D printers. Printer telemetry is the source of truth for print state; OBS owns cameras and video.

## Features
- Multiple Klipper/Moonraker and Bambu Lab LAN-mode printers with reconnect backoff
- Normalized telemetry, event overrides, deterministic rotation, and manual override
- OBS WebSocket v5 scene and stream control with duplicate-action protection
- Event-driven OBS stream/scene tracking with `GetStreamStatus` polling as a watchdog/fallback
- Optional Windows OBS process supervision and automatic launch when OBS is not running
- FastAPI dashboard, transparent per-printer overlays, overview overlay, and live WebSocket updates
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

The dashboard includes a local settings page at `/settings` for overlay appearance, field visibility, profiles, and per-printer card overrides. Changes are saved to `overlay-settings.json` by default. System settings saved through the UI are stored in a local `*.local.json` override next to the active config file. Generated local config, overlay settings, logs, and `.env` are ignored by Git.

Optional local auth is available for shared LAN scenarios via `auth.enabled` and `auth.token_env` (for example `PRINTDIRECTOR_TOKEN`). When enabled, API and overlay WebSocket access require the configured token except for health endpoints and the local settings/preview pages.

### OBS connection settings
`obs.reconnect_interval` controls retry backoff after a lost OBS request/event connection. `obs.status_poll_interval` defaults to 15 seconds. OBS stream and scene events are used as the primary state source; `GetStreamStatus` is retained as a periodic watchdog and as the automatic fallback if the event channel is unavailable.

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

The default `launch_args` is empty, so OBS opens normally. OBS officially supports `--minimize-to-tray` if you want unattended startup:

```yaml
  launch_args:
    - --minimize-to-tray
```

A relaunch cooldown prevents repeated starts while OBS is still initializing. If Windows process detection fails, PrintDirector deliberately does not launch OBS because avoiding duplicate OBS instances is more important than forcing a restart.

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

- `GET /api/health` — process liveness and cached component status; does not force external connections.
- `GET /api/health/ready` — operational readiness. It performs an OBS watchdog query and returns HTTP 503 when the runtime is not running or OBS cannot be reached. Printer online counts are included for diagnostics but an individual offline printer does not make the entire service unready.

These endpoints are suitable for local monitoring or a watchdog task.

## Demo and tests
```powershell
.\.venv\Scripts\Activate.ps1
python -m printdirector.main --demo
pytest -q
```

Demo mode uses configured printer names/scenes but does not contact printer hardware. GitHub Actions runs the test suite and source syntax checks on both Windows and Linux for pushes and pull requests.

## API
Read endpoints include `GET /api/health`, `/api/health/ready`, `/api/printers`, `/api/printers/{id}`, and `/api/director/status`; live updates use `/ws/printers`. Director/stream control endpoints are available for local automation. If `auth.enabled` is enabled, the normal API and WebSocket endpoints require the configured token.

## Windows unattended operation
For long-running use, Task Scheduler is preferable to leaving a PowerShell window open. Create a task that starts at user logon and runs:

- **Program:** `<PrintDirector>\.venv\Scripts\python.exe`
- **Arguments:** `-m printdirector.main --config config.yaml`
- **Start in:** the PrintDirector repository directory

In the task settings, enable **Restart the task if it fails** (for example after 1 minute) and **Run task as soon as possible after a scheduled start is missed**. Because OBS itself normally runs in the interactive desktop session, a user-logon trigger is generally more appropriate than running PrintDirector as a SYSTEM service.

With `obs.auto_launch: true`, a user-logon PrintDirector task can also bring OBS back up if OBS was not running or later exits/crashes. PrintDirector does not terminate OBS when PrintDirector itself shuts down.

If the OBS password exists only as a temporary PowerShell environment variable, Task Scheduler will not inherit it. Use a persistent user environment variable or store the OBS password in PrintDirector's local configuration before relying on unattended startup.

## Troubleshooting
- **Dashboard unavailable:** confirm the process is running and port 8765 is free.
- **Printer offline:** verify the Moonraker/Bambu URL, credentials, trusted clients, and host reachability. Reconnection is automatic.
- **OBS offline:** if auto-launch is disabled, start OBS manually. If auto-launch is enabled, check `logs/printdirector.log` for process-detection or executable-path errors. Also verify WebSocket v5 host/port/password and firewall settings.
- **OBS launches repeatedly:** this should be prevented by process detection and the relaunch cooldown. Stop PrintDirector and collect `logs/printdirector.log` before launching OBS manually.
- **OBS event channel unavailable:** PrintDirector logs a warning and automatically falls back to periodic `GetStreamStatus` polling.
- **Scene does not switch:** scene names are case-sensitive and must match configuration exactly.
- **No layer count:** printer telemetry does not always expose it; the UI intentionally hides unavailable values.
- **PowerShell blocks activation:** use `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.
- **Crash investigation:** collect `logs/printdirector.log`, the OBS session log, and the OBS crash report from the same run. Stream-state transitions and OBS connection lifecycle are recorded in the PrintDirector log.

## Design notes
A future printer adapter can implement `PrinterAdapter` without changing director logic. Bambu Lab support is included for LAN-mode printers; computer vision is intentionally not included. Temporary loss of one printer, an OBS request connection, or the OBS event channel does not terminate the application.
