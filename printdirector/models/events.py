from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class StrEnum(str, Enum):
 pass


class EventType(StrEnum):
 PRINT_STARTED="print_started"; PRINT_PAUSED="print_paused"; PRINT_RESUMED="print_resumed"; PRINT_NEAR_COMPLETE="print_near_complete"; PRINT_COMPLETED="print_completed"; PRINTER_ERROR="printer_error"; PRINTER_OFFLINE="printer_offline"; PRINTER_ONLINE="printer_online"
DEFAULT_PRIORITIES={EventType.PRINTER_ERROR:100,EventType.PRINT_STARTED:80,EventType.PRINT_COMPLETED:70,EventType.PRINT_NEAR_COMPLETE:60,EventType.PRINT_PAUSED:50,EventType.PRINT_RESUMED:55,EventType.PRINTER_OFFLINE:40,EventType.PRINTER_ONLINE:20}
@dataclass(order=True)
class PrinterEvent:
 sort_index:int=field(init=False,repr=False); type:EventType=field(compare=False); printer_id:str=field(compare=False); priority:int=field(default=0,compare=False); created:float=field(default_factory=monotonic,compare=False)
 def __post_init__(self): self.priority=self.priority or DEFAULT_PRIORITIES[self.type]; self.sort_index=-self.priority
