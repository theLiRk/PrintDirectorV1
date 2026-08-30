import asyncio
from datetime import datetime,timezone
from .base import PrinterAdapter
from printdirector.models import PrinterState
class DemoAdapter(PrinterAdapter):
 def __init__(self,i,n,offset=0): super().__init__(i,n); self.offset=offset; self._stop=asyncio.Event()
 async def stop(self): self._stop.set()
 async def run(self):
  p=.15+self.offset
  while not self._stop.is_set():
   state=PrinterState.PRINTING if self.offset==0 or p>.55 else PrinterState.IDLE
   if state==PrinterState.PRINTING: p=(p+.003)%1
   self.status=self.status.model_copy(update={'online':True,'state':state,'filename':'demo_part.gcode' if state==PrinterState.PRINTING else None,'progress':p if state==PrinterState.PRINTING else 0,'elapsed_time':p*7200,'estimated_remaining':(1-p)*7200,'hotend_temperature':210 if state==PrinterState.PRINTING else 25,'hotend_target':210 if state==PrinterState.PRINTING else 0,'bed_temperature':60 if state==PrinterState.PRINTING else 25,'bed_target':60 if state==PrinterState.PRINTING else 0,'current_layer':int(p*200),'total_layers':200,'last_update':datetime.now(timezone.utc)})
   self.publish(); await asyncio.sleep(1)
 async def stop(self): self._stop.set()
