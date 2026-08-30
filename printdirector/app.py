import asyncio
from .printers import PrinterManager
from .obs import OBSClient
from .director import Director
from .config.loader import obs_password
class Runtime:
 def __init__(self,config,demo=False):
  self.config=config; self.manager=PrinterManager(config.printers,demo); self.obs=OBSClient(config.obs,obs_password(config)); self.director=Director(config.director,config.printers,self.obs); self.hub=None; self.tasks=[]
  for a in self.manager.adapters.values(): a.subscribe(self.on_status)
 def on_status(self,s): self.director.update(s)
 async def broadcaster(self):
  while True:
   if self.hub: await self.hub.broadcast({'printers':[s.model_dump(mode='json') for s in self.manager.statuses().values()],'director':self.director.public_status()})
   await asyncio.sleep(1)
 async def start(self): await self.manager.start(); self.tasks=[asyncio.create_task(self.director.run()),asyncio.create_task(self.broadcaster())]
 async def stop(self): await self.director.stop(); await self.manager.stop(); [t.cancel() for t in self.tasks]; await asyncio.gather(*self.tasks,return_exceptions=True); await self.obs.close()
