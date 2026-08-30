import asyncio
from .bambu import BambuAdapter
from .demo import DemoAdapter
from .klipper import KlipperAdapter
class PrinterManager:
 def __init__(self,configs,demo=False):
  self.adapters={}
  for i,p in enumerate(configs):
   if demo:
     adapter=DemoAdapter(p.id,p.name,i*.3)
   elif p.type == 'bambu':
     adapter=BambuAdapter(p.id,p.name,p.bambu_url or p.moonraker_url,p.access_code,p.serial_number)
   else:
     adapter=KlipperAdapter(p.id,p.name,p.moonraker_url)
   self.adapters[p.id]=adapter
  self.tasks=[]
 def statuses(self): return {k:v.status for k,v in self.adapters.items()}
 async def start(self): self.tasks=[asyncio.create_task(a.run(),name=f"printer-{k}") for k,a in self.adapters.items()]
 async def stop(self):
  await asyncio.gather(*(a.stop() for a in self.adapters.values())); [t.cancel() for t in self.tasks]; await asyncio.gather(*self.tasks,return_exceptions=True)
