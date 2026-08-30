from abc import ABC, abstractmethod
from collections.abc import Callable
from printdirector.models import PrinterStatus
class PrinterAdapter(ABC):
 def __init__(self,printer_id:str,printer_name:str): self.printer_id=printer_id; self.printer_name=printer_name; self.status=PrinterStatus(printer_id=printer_id,printer_name=printer_name); self._listeners:list[Callable]=[]
 def subscribe(self,fn:Callable): self._listeners.append(fn)
 def publish(self):
  for fn in self._listeners: fn(self.status)
 @abstractmethod
 async def run(self): ...
 @abstractmethod
 async def stop(self): ...
