import asyncio
import json
import os
import secrets
from pathlib import Path

import aiohttp
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from printdirector.config.models import OverlayThemeConfig
from printdirector.printers.bambu import BambuAdapter

BASE = Path(__file__).parent


class Hub:
 def __init__(self): self.clients=set()
 async def add(self,ws): await ws.accept(); self.clients.add(ws)
 def remove(self,ws): self.clients.discard(ws)
 async def broadcast(self,data):
  dead=[]
  for ws in tuple(self.clients):
   try: await ws.send_json(data)
   except Exception: dead.append(ws)
  for ws in dead:self.remove(ws)


def settings_path(runtime):
 path = Path(runtime.config.overlay.settings_file)
 if not path.is_absolute():
   path = runtime.config_path.parent / path
 return path


def load_style(runtime):
 style = runtime.config.overlay.style
 path = settings_path(runtime)
 if not path.exists():
   return style
 try:
   data = json.loads(path.read_text(encoding='utf-8'))
   return OverlayThemeConfig.model_validate({**style.model_dump(mode='json'), **data})
 except (json.JSONDecodeError, TypeError, ValueError):
   return style


def persist_style(runtime, style):
 path = settings_path(runtime)
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(json.dumps(style.model_dump(mode='json'), indent=2), encoding='utf-8')
 runtime.config.overlay.style = style


def local_config_path(runtime):
 return runtime.config_path.with_suffix('.local.json')


def persist_local_config(runtime, data):
 path = local_config_path(runtime)
 path.parent.mkdir(parents=True, exist_ok=True)
 temp = path.with_suffix(path.suffix + '.tmp')
 temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
 temp.replace(path)


def expected_auth_token(config):
 return (config.auth.token or os.getenv(config.auth.token_env, '')).strip()


def request_token(request):
 auth = request.headers.get('Authorization', '')
 if auth.lower().startswith('bearer '):
   return auth.split(' ', 1)[1].strip()
 return (request.query_params.get('token') or '').strip()


def websocket_token(websocket):
 auth = websocket.headers.get('Authorization', '')
 if auth.lower().startswith('bearer '):
   return auth.split(' ', 1)[1].strip()
 return (websocket.query_params.get('token') or '').strip()


def token_matches(expected, supplied):
 return bool(expected) and secrets.compare_digest(expected, supplied)


def check_auth(config, request: Request):
 if not config.auth.enabled: return
 expected = expected_auth_token(config)
 if not expected:
   raise HTTPException(401, 'Token is not configured')
 if not token_matches(expected, request_token(request)):
   raise HTTPException(401, 'Unauthorized')


def create_app(runtime):
 app = FastAPI(title='PrintDirector API', version='1.0')
 app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')
 hub = Hub(); runtime.hub = hub
 runtime.config.overlay.style = load_style(runtime)

 def all_data(): return [s.model_dump(mode='json') for s in runtime.manager.statuses().values()]

 @app.middleware('http')
 async def auth_middleware(request: Request, call_next):
   if request.url.path.startswith('/static'):
     return await call_next(request)
   if request.url.path in {'/api/health'}:
     return await call_next(request)
   if runtime.config.auth.enabled and request.url.path not in {'/settings', '/preview'}:
     check_auth(runtime.config, request)
   return await call_next(request)

 @app.get('/api/health')
 def health():
  ss = runtime.manager.statuses(); return {'status':'ok','obs_connected':runtime.obs.connected,'configured_printers':len(ss),'online_printers':sum(x.online for x in ss.values())}

 @app.get('/api/printers')
 def printers(request: Request):
  check_auth(runtime.config, request)
  return all_data()

 @app.get('/api/printers/{pid}')
 def printer(pid, request: Request):
  check_auth(runtime.config, request)
  s = runtime.manager.statuses().get(pid)
  if not s: raise HTTPException(404, 'Unknown printer')
  return s

 @app.get('/api/director/status')
 def ds(request: Request):
  check_auth(runtime.config, request)
  return runtime.director.public_status()

 @app.get('/api/settings')
 def settings(request: Request):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  data = runtime.config.overlay.style.model_dump(mode='json')
  data['printer_ids'] = list(runtime.manager.adapters.keys())
  return data

 @app.post('/api/settings')
 def update_settings(request: Request, payload: dict):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  payload = {k:v for k,v in payload.items() if k != 'printer_ids'}
  try:
   style = OverlayThemeConfig.model_validate(payload)
  except ValidationError as exc:
   raise HTTPException(422, f'Invalid overlay settings: {exc}') from exc
  persist_style(runtime, style)
  return {**style.model_dump(mode='json'), 'printer_ids': list(runtime.manager.adapters.keys())}

 async def _probe_bambu(printer: dict, gateway: str):
  adapter = BambuAdapter(
   printer.get('id', 'connection-test'),
   printer.get('name', 'Bambu printer'),
   gateway,
   printer.get('access_code'),
   printer.get('serial_number'),
  )
  try:
   await adapter._connect()
   payload = await asyncio.wait_for(adapter._messages.get(), timeout=10)
   if isinstance(payload, Exception):
     raise payload
   return {'ok': True, 'message': f'Bambu printer connected via MQTT at {gateway}'}
  except Exception as exc:
   raise HTTPException(502, f'Unable to connect to Bambu MQTT at {gateway}: {exc}') from exc
  finally:
   await adapter._disconnect()

 async def _probe_printer(printer: dict):
  printer_type = (printer.get('type') or 'klipper').lower()
  gateway = (printer.get('moonraker_url') or printer.get('bambu_url') or '').strip().rstrip('/')
  if not gateway:
   raise HTTPException(400, 'Printer URL is required')
  if printer_type == 'bambu':
   return await _probe_bambu(printer, gateway)

  headers = {'Accept': 'application/json'}
  candidates = [gateway, f'{gateway}/printer/info', f'{gateway}/api/server', f'{gateway}/server']
  timeout = aiohttp.ClientTimeout(total=5)
  async with aiohttp.ClientSession(timeout=timeout) as session:
   for url in candidates:
    try:
     async with session.get(url, headers=headers) as response:
      if response.status >= 400:
       continue
      body = await response.text()
      if not body.strip():
       continue
      try:
       payload = json.loads(body)
      except json.JSONDecodeError:
       continue
      if isinstance(payload, dict) and ('result' in payload or 'status' in payload or 'server' in payload):
       return {'ok': True, 'message': f'Klipper printer connected at {gateway}'}
    except (aiohttp.ClientError, asyncio.TimeoutError):
     continue
  raise HTTPException(502, 'Unable to reach the Klipper printer at the configured URL')

 @app.post('/api/printers/test')
 async def test_printer(request: Request, payload: dict):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  printer = payload.get('printer') or payload
  if not isinstance(printer, dict):
   raise HTTPException(400, 'Printer payload is required')
  return await _probe_printer(printer)

 @app.get('/api/system-config')
 def system_config(request: Request):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  data = runtime.config.model_dump(mode='json')
  data['obs']['password'] = runtime.config.obs.password
  data['auth']['token'] = runtime.config.auth.token
  return data

 @app.post('/api/system-config')
 async def update_system_config(request: Request, payload: dict):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  payload = dict(payload)
  if 'obs' in payload and isinstance(payload['obs'], dict):
   payload['obs'] = dict(payload['obs'])
   if 'password' in payload['obs'] and not payload['obs']['password']:
     payload['obs']['password'] = runtime.config.obs.password
  if 'auth' in payload and isinstance(payload['auth'], dict):
   payload['auth'] = dict(payload['auth'])
   if 'token' in payload['auth'] and not payload['auth']['token']:
     payload['auth']['token'] = runtime.config.auth.token

  merged = runtime.config.model_dump(mode='json')
  merged = {**merged, **payload}
  for section in ('obs', 'auth', 'director', 'overlay', 'logging'):
   if section in payload and isinstance(payload[section], dict):
    merged[section] = {**runtime.config.model_dump(mode='json').get(section, {}), **payload[section]}
  if 'printers' in payload and isinstance(payload['printers'], list):
   merged['printers'] = payload['printers']

  try:
   new_config = type(runtime.config).model_validate(merged)
  except ValidationError as exc:
   raise HTTPException(422, f'Invalid system configuration: {exc}') from exc

  restart_required = []
  if (new_config.overlay.host, new_config.overlay.port) != (runtime.config.overlay.host, runtime.config.overlay.port):
   restart_required.append('overlay_bind')

  persist_local_config(runtime, merged)
  await runtime.reconfigure(new_config)
  result = runtime.config.model_dump(mode='json')
  if restart_required:
   result['restart_required'] = restart_required
  return result

 @app.post('/api/director/auto/{enabled}')
 def auto(enabled: bool, request: Request):
  check_auth(runtime.config, request)
  runtime.director.auto_enabled = enabled; return runtime.director.public_status()

 @app.post('/api/director/return-auto')
 def ret(request: Request):
  check_auth(runtime.config, request)
  runtime.director.return_auto(); return runtime.director.public_status()

 @app.post('/api/director/show/{target}')
 async def show(target, request: Request):
  check_auth(runtime.config, request)
  if target == 'overview': scene = runtime.config.director.overview_scene; pid = None
  elif target == 'idle': scene = runtime.config.director.idle_scene; pid = None
  elif target in runtime.director.scenes: scene = runtime.director.scenes[target]; pid = target
  else: raise HTTPException(404, 'Unknown target')
  await runtime.director.command_scene(scene, pid); return runtime.director.public_status()

 @app.post('/api/stream/{action}')
 async def stream(action, request: Request):
  check_auth(runtime.config, request)
  if action == 'start': await runtime.obs.start_stream()
  elif action == 'stop': await runtime.obs.stop_stream()
  else: raise HTTPException(400, 'Use start or stop')
  return runtime.director.public_status()

 @app.websocket('/ws/printers')
 async def ws(websocket: WebSocket):
  if runtime.config.auth.enabled:
   expected = expected_auth_token(runtime.config)
   if not expected or not token_matches(expected, websocket_token(websocket)):
    await websocket.close(code=1008, reason='Unauthorized')
    return
  await hub.add(websocket)
  try:
   await websocket.send_json({'printers': all_data(), 'director': runtime.director.public_status()})
   while True: await websocket.receive_text()
  except WebSocketDisconnect:
   pass
  finally:
   hub.remove(websocket)

 @app.get('/', response_class=HTMLResponse)
 def dash(): return (BASE/'templates/dashboard.html').read_text(encoding='utf-8')

 @app.get('/settings', response_class=HTMLResponse)
 def settings_page(): return (BASE/'templates/settings.html').read_text(encoding='utf-8')

 @app.get('/preview', response_class=HTMLResponse)
 def preview_page(): return (BASE/'templates/preview.html').read_text(encoding='utf-8')

 @app.get('/overlay/overview', response_class=HTMLResponse)
 def overview(): return (BASE/'templates/overview.html').read_text(encoding='utf-8')

 @app.get('/overlay/{pid}', response_class=HTMLResponse)
 def overlay(pid):
  if pid not in runtime.manager.adapters: raise HTTPException(404, 'Unknown printer')
  return (BASE/'templates/printer.html').read_text(encoding='utf-8').replace('__PRINTER_ID__', pid)

 return app
