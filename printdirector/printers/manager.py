import asyncio
from .klipper import KlipperAdapter
from .demo import DemoAdapter
class PrinterManager:
 def __init__(self,configs,demo=False):
  self.adapters={p.id:(DemoAdapter(p.id,p.name,i*.3) if demo else KlipperAdapter(p.id,p.name,p.moonraker_url)) for i,p in enumerate(configs)}; self.tasks=[]
 def statuses(self): return {k:v.status for k,v in self.adapters.items()}
 async def start(self): self.tasks=[asyncio.create_task(a.run(),name=f"printer-{k}") for k,a in self.adapters.items()]
 async def stop(self):
  await asyncio.gather(*(a.stop() for a in self.adapters.values())); [t.cancel() for t in self.tasks]; await asyncio.gather(*self.tasks,return_exceptions=True)
