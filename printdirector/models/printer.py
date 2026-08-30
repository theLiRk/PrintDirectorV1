from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from pydantic import BaseModel, Field
class PrinterState(StrEnum):
    OFFLINE="offline"; IDLE="idle"; PRINTING="printing"; PAUSED="paused"; COMPLETE="complete"; ERROR="error"
class PrinterStatus(BaseModel):
    printer_id:str; printer_name:str; state:PrinterState=PrinterState.OFFLINE; filename:str|None=None
    progress:float=Field(0,ge=0,le=1); elapsed_time:float=0; estimated_remaining:float|None=None
    hotend_temperature:float|None=None; hotend_target:float|None=None; bed_temperature:float|None=None; bed_target:float|None=None
    print_speed:float|None=None; current_layer:int|None=None; total_layers:int|None=None
    last_update:datetime=Field(default_factory=lambda:datetime.now(timezone.utc)); online:bool=False
