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
### Windows PowerShell
```powershell
git clone https://github.com/theLiRk/PrintDirectorV1 PrintDirector
cd PrintDirector
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
$env:OBS_WEBSOCKET_PASSWORD="your-password"
python -m printdirector.main
```
Every new PowerShell session must run `.\.venv\Scripts\Activate.ps1` after entering the project directory.

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp config.example.yaml config.yaml
export OBS_WEBSOCKET_PASSWORD='your-password'
python -m printdirector.main
```

## Configuration
Edit `config.yaml`. Add any number of printers. IDs must be unique and URL-safe. The default dashboard binds to `127.0.0.1`; change this only on a trusted LAN. Secrets come from environment variables, not YAML.

Moonraker normally listens on port 7125. Find its host address in Mainsail/Fluidd, your router, or the printer host. Verify it locally by opening `http://HOST:7125/printer/info`. If Moonraker authorization restricts your client, allow the PrintDirector host in Moonraker's trusted clients.

## OBS setup
In OBS, open **Tools > WebSocket Server Settings**, enable the server, keep port 4455 unless configured otherwise, and set a password matching `OBS_WEBSOCKET_PASSWORD`.

Create these scenes exactly as configured:
- `PrintDirector Idle`
- `Printer - Printer 1`
- `Printer - Printer 2`
- `Print Farm Overview`

Add camera sources manually. PrintDirector never captures or analyzes video. Suggested structure:
```text
Printer - Printer 1
  Printer 1 Camera
  Printer 1 Overlay (Browser Source)
Printer - Printer 2
  Printer 2 Camera
  Printer 2 Overlay (Browser Source)
Print Farm Overview
  Camera sources
  Farm Overview (Browser Source)
```
Browser Source URLs:
- Per printer: `http://127.0.0.1:8765/overlay/printer1`
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
A future adapter can implement `PrinterAdapter` without changing director logic. Bambu Lab and computer vision are intentionally not included. Temporary loss of one printer or OBS does not terminate the application.
