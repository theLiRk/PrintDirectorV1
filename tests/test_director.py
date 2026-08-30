import asyncio
from types import SimpleNamespace
from printdirector.director import Director
from printdirector.config.models import DirectorConfig
from printdirector.models import PrinterStatus,PrinterState
class OBS:
 def __init__(self):self.connected=True;self.streaming=False;self.current_scene=None
 async def set_scene(self,s):self.current_scene=s
 async def is_streaming(self):return self.streaming
 async def start_stream(self):self.streaming=True
 async def stop_stream(self):self.streaming=False
P=lambda i,s:PrinterStatus(printer_id=i,printer_name=i,state=s,online=True)
def make(**kw):
 cfg=DirectorConfig(rotation_interval=1,**kw); pcs=[SimpleNamespace(id='a',obs=SimpleNamespace(scene='A')),SimpleNamespace(id='b',obs=SimpleNamespace(scene='B'))];return Director(cfg,pcs,OBS())
def test_rotation_and_removal():
 async def run():
  d=make();d.update(P('a',PrinterState.PRINTING));d.update(P('b',PrinterState.PRINTING));await d.tick(10);first=d.obs.current_scene;await d.tick(12);assert d.obs.current_scene!=first;d.update(P('b',PrinterState.IDLE));await d.tick(14);assert d.obs.current_scene=='A'
 asyncio.run(run())
def test_manual_return_auto():
 async def run():
  d=make();d.update(P('a',PrinterState.PRINTING));await d.command_scene('B','b');await d.tick(10);assert d.obs.current_scene=='B';d.return_auto();await d.tick(11);assert d.obs.current_scene=='A'
 asyncio.run(run())
def test_stream_start_stop_grace():
 async def run():
  d=make(auto_start_stream=True,auto_stop_stream=True,stream_stop_delay=5);d.update(P('a',PrinterState.PRINTING));await d.tick(1);assert d.obs.streaming;d.update(P('a',PrinterState.IDLE));await d.tick(2);await d.tick(8);assert not d.obs.streaming
 asyncio.run(run())
