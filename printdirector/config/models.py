from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

class PrinterOBSConfig(BaseModel): scene:str; camera_source:Optional[str]=None

class PrinterConfig(BaseModel):
 id:str=Field(pattern=r"^[a-zA-Z0-9_-]+$"); name:str; type:Literal["klipper","bambu"]="klipper"; moonraker_url:Optional[str]=None; bambu_url:Optional[str]=None; access_code:Optional[str]=None; serial_number:Optional[str]=None; obs:PrinterOBSConfig

 @model_validator(mode="after")
 def validate_url(self):
   if self.type == "bambu":
     if not self.bambu_url and not self.moonraker_url:
       raise ValueError("Bambu printers require a bambu_url or moonraker_url")
     if not self.access_code:
       raise ValueError("Bambu printers require access_code")
     if not self.serial_number:
       raise ValueError("Bambu printers require serial_number")
     return self
   if not self.moonraker_url:
     raise ValueError("Klipper printers require moonraker_url")
   return self

class OBSConfig(BaseModel): host:str="127.0.0.1"; port:int=4455; password_env:str="OBS_WEBSOCKET_PASSWORD"; password:Optional[str]=None; reconnect_interval:float=5

class DirectorConfig(BaseModel):
 enabled:bool=True; rotation_interval:float=30; idle_scene:str="PrintDirector Idle"; overview_scene:str="Print Farm Overview"; auto_start_stream:bool=False; auto_stop_stream:bool=False; stream_stop_delay:float=300; near_complete_threshold:float=.95
 event_hold_times:dict[str,float]=Field(default_factory=lambda:{"print_started":30,"print_completed":45,"print_near_complete":60,"printer_error":120,"print_paused":30})

class PrinterCardConfig(BaseModel):
 accent_color:Optional[str]=None
 text_color:Optional[str]=None
 panel_opacity:Optional[float]=Field(default=None,ge=0.2,le=1.0)
 font_scale:Optional[float]=Field(default=None,ge=0.8,le=1.5)
 show_filename:Optional[bool]=None
 show_state:Optional[bool]=None
 show_eta:Optional[bool]=None
 show_temps:Optional[bool]=None
 show_layers:Optional[bool]=None
 label_override:Optional[str]=None

class OverlayThemeConfig(BaseModel):
 theme:str="dark"
 background_color:str="#0b0e14"
 text_color:str="#f5f7fa"
 accent_color:str="#38bdf8"
 panel_opacity:float=Field(0.92,ge=0.2,le=1.0)
 font_family:str="system-ui"
 font_scale:float=Field(1.0,ge=0.8,le=1.5)
 show_filename:bool=True
 show_state:bool=True
 show_eta:bool=True
 show_temps:bool=True
 show_layers:bool=True
 printer_overrides:dict[str, PrinterCardConfig]=Field(default_factory=dict)

class AuthConfig(BaseModel):
 enabled:bool=False
 token_env:str="PRINTDIRECTOR_TOKEN"
 token:Optional[str]=None

class OverlayConfig(BaseModel):
 host:str="127.0.0.1"; port:int=8765; allow_lan:bool=False; settings_file:str="overlay-settings.json"
 style:OverlayThemeConfig=Field(default_factory=OverlayThemeConfig)

 @model_validator(mode="after")
 def validate_host(self):
   if self.allow_lan: return self
   local_hosts={"127.0.0.1","localhost","::1"}
   if self.host not in local_hosts:
     raise ValueError("Overlay host must be localhost/127.0.0.1 unless allow_lan is enabled")
   return self

class LoggingConfig(BaseModel): level:str="INFO"

class AppConfig(BaseModel):
 printers:list[PrinterConfig]; obs:OBSConfig=OBSConfig(); director:DirectorConfig=DirectorConfig(); overlay:OverlayConfig=OverlayConfig(); auth:AuthConfig=AuthConfig(); logging:LoggingConfig=LoggingConfig()

 @model_validator(mode="after")
 def unique(self):
  ids=[p.id for p in self.printers]
  if len(ids)!=len(set(ids)): raise ValueError("Printer IDs must be unique")
  return self
