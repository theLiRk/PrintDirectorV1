# PrintDirector

PrintDirector is a local, asynchronous OBS director for multiple 3D printers. Moonraker is the source of truth; OBS owns cameras and video.

## Features
- Multiple Klipper/Moonraker printers with WebSocket subscriptions and reconnect backoff
- Normalized telemetry, event overrides, deterministic rotation, manual override
- OBS WebSocket v5 scene and stream control with failure isolation
- FastAPI dashboard, transparent per-printer overlays, overview overlay, live WebSocket updates
- Demo mode and unit tests

## Requirements
Python 3.11+, Moonraker, and OBS Studio with WebSocket v5 enabled. OBS 28+ includes obs-websocket.

## Install
The project now includes setup helpers for first-run installation.

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

This bypass applies only to the current PowerShell session and does not change
the machine-wide execution policy. If Windows marked the downloaded script as
blocked, run `Unblock-File .\install.ps1` first.

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
Edit `config.yaml`. Add any number of printers. IDs must be unique and URL-safe. The default dashboard binds to `127.0.0.1`; change this only on a trusted LAN and enable `overlay.allow_lan` intentionally. Secrets come from environment variables, not YAML.

The dashboard includes a local settings page at `/settings` for overlay appearance, field visibility, profiles, and per-printer card overrides. Changes are saved to `overlay-settings.json` by default.

Optional local auth is available for shared LAN scenarios via `auth.enabled` and `auth.token_env` (for example `PRINTDIRECTOR_TOKEN`). When enabled, the state-changing API endpoints require a bearer token.

Moonraker normally listens on port 7125. Find its host address in Mainsail/Fluidd, your router, or the printer host. Verify it locally by opening `http://HOST:7125/printer/info`. If Moonraker authorization restricts your client, allow the PrintDirector host in Moonraker's trusted clients.

## OBS setup
In OBS, open **Tools > WebSocket Server Settings**, enable the server, keep port 4455 unless configured otherwise, and set a password matching `OBS_WEBSOCKET_PASSWORD`.

Create these scenes exactly as configured:
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

## Demo and tests
```powershell
.\.venv\Scripts\Activate.ps1
python -m printdirector.main --demo
pytest -q
```
Demo mode uses configured printer names/scenes but does not contact hardware.

## API
`GET /api/health`, `/api/printers`, `/api/printers/{id}`, `/api/director/status`; live updates use `/ws/printers`. Control endpoints are intentionally unauthenticated and must remain on a trusted local interface.

## Troubleshooting
- **Dashboard unavailable:** confirm the process is running and port 8765 is free.
- **Printer offline:** verify the Moonraker URL, port, trusted clients, and host reachability. Reconnection is automatic.
- **OBS offline:** start OBS, enable WebSocket v5, verify host/port/password and firewall. Reconnection occurs on the next request.
- **Scene does not switch:** scene names are case-sensitive and must match YAML exactly.
- **No layer count:** Klipper metadata does not always expose it; the UI intentionally hides unavailable values.
- **PowerShell blocks activation:** use `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.

## Design notes
A future adapter can implement `PrinterAdapter` without changing director logic. Bambu Lab support is included for LAN-mode printers; computer vision is intentionally not included. Temporary loss of one printer or OBS does not terminate the application.
