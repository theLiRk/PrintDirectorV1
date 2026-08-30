from pathlib import Path
from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
BASE=Path(__file__).parent
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
def create_app(runtime):
 app=FastAPI(title='PrintDirector API',version='1.0'); app.mount('/static',StaticFiles(directory=BASE/'static'),name='static'); hub=Hub(); runtime.hub=hub
 def all_data(): return [s.model_dump(mode='json') for s in runtime.manager.statuses().values()]
 @app.get('/api/health')
 def health():
  ss=runtime.manager.statuses(); return {'status':'ok','obs_connected':runtime.obs.connected,'configured_printers':len(ss),'online_printers':sum(x.online for x in ss.values())}
 @app.get('/api/printers')
 def printers(): return all_data()
 @app.get('/api/printers/{pid}')
 def printer(pid):
  s=runtime.manager.statuses().get(pid)
  if not s: raise HTTPException(404,'Unknown printer')
  return s
 @app.get('/api/director/status')
 def ds(): return runtime.director.public_status()
 @app.post('/api/director/auto/{enabled}')
 def auto(enabled:bool): runtime.director.auto_enabled=enabled; return runtime.director.public_status()
 @app.post('/api/director/return-auto')
 def ret(): runtime.director.return_auto(); return runtime.director.public_status()
 @app.post('/api/director/show/{target}')
 async def show(target):
  if target=='overview': scene=runtime.config.director.overview_scene; pid=None
  elif target=='idle': scene=runtime.config.director.idle_scene; pid=None
  elif target in runtime.director.scenes: scene=runtime.director.scenes[target]; pid=target
  else: raise HTTPException(404,'Unknown target')
  await runtime.director.command_scene(scene,pid); return runtime.director.public_status()
 @app.post('/api/stream/{action}')
 async def stream(action):
  if action=='start': await runtime.obs.start_stream()
  elif action=='stop': await runtime.obs.stop_stream()
  else: raise HTTPException(400,'Use start or stop')
  return runtime.director.public_status()
 @app.websocket('/ws/printers')
 async def ws(websocket:WebSocket):
  await hub.add(websocket)
  try:
   await websocket.send_json({'printers':all_data(),'director':runtime.director.public_status()})
   while True: await websocket.receive_text()
  except WebSocketDisconnect: hub.remove(websocket)
 @app.get('/',response_class=HTMLResponse)
 def dash(): return (BASE/'templates/dashboard.html').read_text()
 @app.get('/overlay/overview',response_class=HTMLResponse)
 def overview(): return (BASE/'templates/overview.html').read_text()
 @app.get('/overlay/{pid}',response_class=HTMLResponse)
 def overlay(pid):
  if pid not in runtime.manager.adapters: raise HTTPException(404,'Unknown printer')
  return (BASE/'templates/printer.html').read_text().replace('__PRINTER_ID__',pid)
 return app
