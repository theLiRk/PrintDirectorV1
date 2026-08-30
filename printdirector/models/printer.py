from __future__ import annotations
from datetime import datetime,timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class StrEnum(str, Enum):
    pass

class PrinterState(StrEnum):
    OFFLINE="offline"; IDLE="idle"; PRINTING="printing"; PAUSED="paused"; COMPLETE="complete"; ERROR="error"

class PrinterStatus(BaseModel):
    printer_id:str; printer_name:str; state:PrinterState=PrinterState.OFFLINE; filename:Optional[str]=None
    progress:float=Field(0,ge=0,le=1); elapsed_time:float=0; estimated_remaining:Optional[float]=None
    hotend_temperature:Optional[float]=None; hotend_target:Optional[float]=None; bed_temperature:Optional[float]=None; bed_target:Optional[float]=None
    print_speed:Optional[float]=None; current_layer:Optional[int]=None; total_layers:Optional[int]=None
    last_update:datetime=Field(default_factory=lambda:datetime.now(timezone.utc)); online:bool=False