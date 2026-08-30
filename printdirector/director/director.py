import asyncio,logging
from time import monotonic
from printdirector.models import PrinterState,PrinterEvent,EventType
log=logging.getLogger(__name__)
class Director:
 def __init__(self,config,printer_configs,obs):
  self.cfg=config; self.obs=obs; self.scenes={p.id:p.obs.scene for p in printer_configs}; self.statuses={}; self.previous={}; self.auto_enabled=config.enabled; self.manual_scene=None; self.current_printer=None; self.override=None; self.override_until=0; self.rotation=[]; self.index=-1; self.last_switch=0; self.inactive_since=None; self._near=set(); self._stop=asyncio.Event()
 def update(self,s):
  old=self.previous.get(s.printer_id); self.statuses[s.printer_id]=s
  if old: self._events(old,s)
  self.previous[s.printer_id]=s.model_copy(deep=True)
 def _events(self,o,n):
  et=None
  if not o.online and n.online: et=EventType.PRINTER_ONLINE
  elif o.online and not n.online: et=EventType.PRINTER_OFFLINE
  elif n.state==PrinterState.ERROR and o.state!=n.state: et=EventType.PRINTER_ERROR
  elif n.state==PrinterState.PRINTING and o.state not in (PrinterState.PRINTING,PrinterState.PAUSED): et=EventType.PRINT_STARTED
  elif n.state==PrinterState.PAUSED and o.state!=n.state: et=EventType.PRINT_PAUSED
  elif n.state==PrinterState.PRINTING and o.state==PrinterState.PAUSED: et=EventType.PRINT_RESUMED
  elif n.state==PrinterState.COMPLETE and o.state!=n.state: et=EventType.PRINT_COMPLETED
  if n.progress>=self.cfg.near_complete_threshold and n.printer_id not in self._near: et=EventType.PRINT_NEAR_COMPLETE; self._near.add(n.printer_id)
  if n.progress<.1 and n.state!=PrinterState.COMPLETE: self._near.discard(n.printer_id)
  if et: self.handle_event(PrinterEvent(et,n.printer_id))
 def handle_event(self,e):
  hold=self.cfg.event_hold_times.get(e.type.value,0)
  if hold and (not self.override or e.priority>=self.override.priority): self.override=e; self.override_until=monotonic()+hold
 async def command_scene(self,scene,printer=None): self.manual_scene=scene; self.auto_enabled=False; self.current_printer=printer; await self.obs.set_scene(scene)
 def return_auto(self): self.manual_scene=None; self.auto_enabled=True
 def active_ids(self): return sorted(k for k,v in self.statuses.items() if v.state in (PrinterState.PRINTING,PrinterState.PAUSED))
 async def tick(self,now=None):
  now=now or monotonic(); active=self.active_ids()
  if active: self.inactive_since=None
  elif self.inactive_since is None: self.inactive_since=now
  await self._stream(active,now)
  if not self.auto_enabled: return
  if self.override and now<self.override_until: await self._show(self.override.printer_id); return
  self.override=None
  if not active: await self.obs.set_scene(self.cfg.idle_scene); self.current_printer=None; return
  self.rotation=active
  if len(active)==1: await self._show(active[0]); return
  if now-self.last_switch>=self.cfg.rotation_interval or self.current_printer not in active:
   self.index=(self.index+1)%len(active); await self._show(active[self.index]); self.last_switch=now
 async def _show(self,pid): self.current_printer=pid; await self.obs.set_scene(self.scenes[pid])
 async def _stream(self,active,now):
  streaming=await self.obs.is_streaming()
  if active and self.cfg.auto_start_stream and not streaming: await self.obs.start_stream()
  if not active and self.cfg.auto_stop_stream and streaming and self.inactive_since is not None and now-self.inactive_since>=self.cfg.stream_stop_delay: await self.obs.stop_stream(); self.inactive_since=now
 async def run(self):
  while not self._stop.is_set():
   try: await self.tick()
   except Exception: log.exception("Director tick failed")
   await asyncio.sleep(1)
 async def stop(self): self._stop.set()
 def public_status(self): return {'auto_enabled':self.auto_enabled,'manual_scene':self.manual_scene,'current_printer':self.current_printer,'current_event':self.override.type.value if self.override else None,'obs_connected':self.obs.connected,'obs_streaming':self.obs.streaming,'current_scene':self.obs.current_scene}
