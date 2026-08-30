from pydantic import BaseModel, Field, model_validator
class PrinterOBSConfig(BaseModel): scene:str; camera_source:str|None=None
class PrinterConfig(BaseModel):
 id:str=Field(pattern=r"^[a-zA-Z0-9_-]+$"); name:str; type:str="klipper"; moonraker_url:str; obs:PrinterOBSConfig
class OBSConfig(BaseModel): host:str="127.0.0.1"; port:int=4455; password_env:str="OBS_WEBSOCKET_PASSWORD"; reconnect_interval:float=5
class DirectorConfig(BaseModel):
 enabled:bool=True; rotation_interval:float=30; idle_scene:str="PrintDirector Idle"; overview_scene:str="Print Farm Overview"; auto_start_stream:bool=False; auto_stop_stream:bool=False; stream_stop_delay:float=300; near_complete_threshold:float=.95
 event_hold_times:dict[str,float]=Field(default_factory=lambda:{"print_started":30,"print_completed":45,"print_near_complete":60,"printer_error":120,"print_paused":30})
class OverlayConfig(BaseModel): host:str="127.0.0.1"; port:int=8765
class LoggingConfig(BaseModel): level:str="INFO"
class AppConfig(BaseModel):
 printers:list[PrinterConfig]; obs:OBSConfig=OBSConfig(); director:DirectorConfig=DirectorConfig(); overlay:OverlayConfig=OverlayConfig(); logging:LoggingConfig=LoggingConfig()
 @model_validator(mode="after")
 def unique(self):
  ids=[p.id for p in self.printers]
  if len(ids)!=len(set(ids)): raise ValueError("Printer IDs must be unique")
  return self
