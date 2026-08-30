from printdirector.models import *
def test_priority(): assert PrinterEvent(EventType.PRINTER_ERROR,'x').priority>PrinterEvent(EventType.PRINT_PAUSED,'x').priority
