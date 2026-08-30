import asyncio
import json
import os
from pathlib import Path

import aiohttp
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from printdirector.config.models import OverlayThemeConfig
from printdirector.printers.bambu import BambuAdapter

BASE = Path(__file__).parent


class Hub:
 def __init__(self): self.clients=set()
 async def add(self,ws): await ws.accept(); self.clients.add(ws)
 def remove(self,ws): self.clients.discard(ws)
 async def broadcast(self,data):
  dead=[]
  for ws in self.clients:
   try: await ws.send_json(data)
   except Exception: dead.append(ws)
  for ws in dead:self.remove(ws)


def settings_path(config):
 path = Path(config.overlay.settings_file)
 if not path.is_absolute():
   path = Path.cwd() / path
 return path


def load_style(config):
 style = config.overlay.style
 path = settings_path(config)
 if not path.exists():
   return style
 try:
   data = json.loads(path.read_text(encoding='utf-8'))
   return OverlayThemeConfig.model_validate({**style.model_dump(mode='json'), **data})
 except (json.JSONDecodeError, TypeError, ValueError):
   return style


def persist_style(config, style):
 path = settings_path(config)
 path.write_text(json.dumps(style.model_dump(mode='json'), indent=2), encoding='utf-8')
 config.overlay.style = style


def local_config_path():
 return Path.cwd() / 'config.local.json'


def load_local_config():
 path = local_config_path()
 if not path.exists():
   return {}
 try:
   data = json.loads(path.read_text(encoding='utf-8'))
   return data if isinstance(data, dict) else {}
 except (json.JSONDecodeError, TypeError):
   return {}


def persist_local_config(data):
 path = local_config_path(); path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def check_auth(config, request: Request):
 if not config.auth.enabled: return
 expected = os.getenv(config.auth.token_env, '')
 if not expected:
   raise HTTPException(401, 'Token is not configured')
 auth = request.headers.get('Authorization', '')
 token = request.query_params.get('token')
 if auth.lower().startswith('bearer '):
   token = auth.split(' ', 1)[1].strip()
 if token != expected:
   raise HTTPException(401, 'Unauthorized')


def create_app(runtime):
 app = FastAPI(title='PrintDirector API', version='1.0')
 app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')
 hub = Hub(); runtime.hub = hub
 runtime.config.overlay.style = load_style(runtime.config)

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
  style = OverlayThemeConfig.model_validate(payload)
  persist_style(runtime.config, style)
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
   adapter._connect()
   await asyncio.wait_for(adapter._messages.get(), timeout=10)
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
  headers = {'Accept': 'application/json'}
  if printer_type == 'bambu':
   return await _probe_bambu(printer, gateway)
   access_code = (printer.get('access_code') or '').strip()
   serial_number = (printer.get('serial_number') or '').strip()
   if access_code: headers['X-Access-Code'] = access_code; headers['Authorization'] = f'Bearer {access_code}'
   if serial_number: headers['X-Serial-Number'] = serial_number; headers['X-Device-Serial'] = serial_number
   candidates = [gateway, f'{gateway}/api/version', f'{gateway}/api/v1/info', f'{gateway}/api/v1/status', f'{gateway}/api/v1/device']
   for url in candidates:
     try:
       async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
         async with session.get(url, headers=headers) as response:
           if response.status in (401,403):
             raise HTTPException(401, 'Printer rejected the credentials')
           if response.status >= 400:
             continue
           body = await response.text()
           if not body.strip():
             continue
           try: json.loads(body)
           except json.JSONDecodeError: continue
           return {'ok': True, 'message': f'Bambu printer connected at {gateway}'}
     except Exception:
       continue
   raise HTTPException(502, 'Unable to reach the Bambu printer with the configured credentials')
  candidates = [gateway, f'{gateway}/printer/info', f'{gateway}/api/server', f'{gateway}/server']
  for url in candidates:
   try:
     async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
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
   except Exception:
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
 def update_system_config(request: Request, payload: dict):
  if runtime.config.auth.enabled: check_auth(runtime.config, request)
  if 'obs' in payload and isinstance(payload['obs'], dict):
   if 'password' in payload['obs'] and not payload['obs']['password']:
     payload['obs']['password'] = runtime.config.obs.password
  if 'auth' in payload and isinstance(payload['auth'], dict):
   if 'token' in payload['auth'] and not payload['auth']['token']:
     payload['auth']['token'] = runtime.config.auth.token
  merged = runtime.config.model_dump(mode='json')
  merged = {**merged, **payload}
  if 'obs' in payload and isinstance(payload['obs'], dict):
   merged['obs'] = {**merged.get('obs', {}), **payload['obs']}
  if 'auth' in payload and isinstance(payload['auth'], dict):
   merged['auth'] = {**merged.get('auth', {}), **payload['auth']}
  if 'printers' in payload and isinstance(payload['printers'], list):
   merged['printers'] = payload['printers']
  persist_local_config(merged)
  runtime.config = runtime.config.model_validate(merged)
  return runtime.config.model_dump(mode='json')

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
  await hub.add(websocket)
  try:
   await websocket.send_json({'printers': all_data(), 'director': runtime.director.public_status()})
   while True: await websocket.receive_text()
  except WebSocketDisconnect: hub.remove(websocket)

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
