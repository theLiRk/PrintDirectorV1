import asyncio,json,logging
from datetime import datetime,timezone
from urllib.parse import urlparse
import aiohttp
from .base import PrinterAdapter
from printdirector.models import PrinterState
log=logging.getLogger(__name__)
OBJECTS={"print_stats":["state","filename","print_duration","total_duration","info"],"display_status":["progress"],"extruder":["temperature","target"],"heater_bed":["temperature","target"],"gcode_move":["speed_factor"],"virtual_sdcard":["progress"],"toolhead":["homed_axes"]}
class KlipperAdapter(PrinterAdapter):
 def __init__(self,printer_id,printer_name,url): super().__init__(printer_id,printer_name); self.url=url.rstrip('/'); self._stop=asyncio.Event(); self._data={}; self._near=False
 async def stop(self): self._stop.set()
 async def run(self):
  delay=1
  while not self._stop.is_set():
   try:
    await self._connect(); delay=1
   except asyncio.CancelledError: raise
   except Exception as e:
    if self.status.online: log.warning("%s connection lost: %s",self.printer_name,e)
    self.status.online=False; self.status.state=PrinterState.OFFLINE; self.publish()
    try: await asyncio.wait_for(self._stop.wait(),delay)
    except asyncio.TimeoutError: pass
    delay=min(delay*2,30)
 async def _connect(self):
  wsurl=self.url.replace('http://','ws://').replace('https://','wss://')+'/websocket'
  async with aiohttp.ClientSession() as s:
   async with s.ws_connect(wsurl,heartbeat=20,timeout=10) as ws:
    log.info("%s connected to Moonraker",self.printer_name)
    await ws.send_json({"jsonrpc":"2.0","method":"printer.objects.subscribe","params":{"objects":OBJECTS},"id":1})
    async for msg in ws:
     if self._stop.is_set(): return
     if msg.type==aiohttp.WSMsgType.TEXT:
      payload=json.loads(msg.data)
      if payload.get('id')==1: self._merge(payload.get('result',{}).get('status',{}))
      elif payload.get('method')=='notify_status_update': self._merge(payload.get('params',[{}])[0])
      elif payload.get('method') in ('notify_klippy_shutdown','notify_klippy_disconnected'): raise ConnectionError(payload['method'])
     elif msg.type in (aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR): raise ConnectionError('websocket closed')
 def _merge(self,change):
  for k,v in change.items(): self._data.setdefault(k,{}).update(v or {})
  ps=self._data.get('print_stats',{}); raw=str(ps.get('state','standby')).lower()
  states={'printing':PrinterState.PRINTING,'paused':PrinterState.PAUSED,'complete':PrinterState.COMPLETE,'error':PrinterState.ERROR,'cancelled':PrinterState.IDLE,'standby':PrinterState.IDLE}
  progress=float(self._data.get('display_status',{}).get('progress',self._data.get('virtual_sdcard',{}).get('progress',0)) or 0)
  elapsed=float(ps.get('print_duration',0) or 0); eta=(elapsed/progress-elapsed) if progress>.001 else None
  info=ps.get('info') or {}; cur=info.get('current_layer'); total=info.get('total_layer') or info.get('total_layers')
  self.status=self.status.model_copy(update={'state':states.get(raw,PrinterState.ERROR),'filename':ps.get('filename') or None,'progress':max(0,min(1,progress)),'elapsed_time':elapsed,'estimated_remaining':max(0,eta) if eta is not None else None,'hotend_temperature':self._data.get('extruder',{}).get('temperature'),'hotend_target':self._data.get('extruder',{}).get('target'),'bed_temperature':self._data.get('heater_bed',{}).get('temperature'),'bed_target':self._data.get('heater_bed',{}).get('target'),'print_speed':float(self._data.get('gcode_move',{}).get('speed_factor',1))*100,'current_layer':cur,'total_layers':total,'online':True,'last_update':datetime.now(timezone.utc)})
  self.publish()
