from printdirector.printers.klipper import KlipperAdapter
from printdirector.models import PrinterState
def test_normalization():
 a=KlipperAdapter('x','X','http://x');a._merge({'print_stats':{'state':'printing','filename':'a.gcode','print_duration':50},'display_status':{'progress':.5}})
 assert a.status.state==PrinterState.PRINTING and a.status.estimated_remaining==50
