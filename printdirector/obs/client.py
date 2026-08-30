import asyncio,logging
import obsws_python as obs
log=logging.getLogger(__name__)
class OBSClient:
 def __init__(self,cfg,password): self.cfg=cfg; self.password=password; self.client=None; self.connected=False; self.streaming=False; self.current_scene=None; self._lock=asyncio.Lock()
 async def _call(self,name,*args):
  async with self._lock:
   try:
    if not self.client: self.client=await asyncio.to_thread(obs.ReqClient,host=self.cfg.host,port=self.cfg.port,password=self.password,timeout=3); self.connected=True; log.info("OBS connected")
    return await asyncio.to_thread(getattr(self.client,name),*args)
   except Exception as e: self.connected=False; self.client=None; log.warning("OBS unavailable: %s",e); return None
 async def set_scene(self,scene):
  if scene==self.current_scene and self.connected:return
  r=await self._call('set_current_program_scene',scene)
  if self.connected: self.current_scene=scene; log.info("OBS scene -> %s",scene)
 async def get_current_scene(self):
  r=await self._call('get_current_program_scene'); self.current_scene=getattr(r,'current_program_scene_name',self.current_scene); return self.current_scene
 async def is_streaming(self):
  r=await self._call('get_stream_status'); self.streaming=bool(getattr(r,'output_active',False)) if r else self.streaming; return self.streaming
 async def start_stream(self):
  if not await self.is_streaming(): await self._call('start_stream'); self.streaming=self.connected
 async def stop_stream(self):
  if await self.is_streaming(): await self._call('stop_stream'); self.streaming=False
 async def close(self): self.client=None; self.connected=False
