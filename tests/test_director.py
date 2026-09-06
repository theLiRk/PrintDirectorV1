import asyncio
from types import SimpleNamespace

from printdirector.config.models import DirectorConfig
from printdirector.director import Director
from printdirector.models import EventType, PrinterState, PrinterStatus


class OBS:
    def __init__(self):
        self.connected = True
        self.streaming = False
        self.current_scene = None
        self.stream_state = "stopped"
        self.status_calls = 0
        self.events = []

    async def set_scene(self, scene):
        self.events.append(("set_scene", scene))
        self.current_scene = scene
        return True

    async def get_current_scene(self):
        self.events.append(("confirm_scene", self.current_scene))
        return self.current_scene

    async def is_streaming(self):
        self.status_calls += 1
        self.events.append(("stream_status", self.streaming))
        return self.streaming

    async def start_stream(self):
        self.events.append(("start_stream", self.current_scene))
        self.streaming = True

    async def stop_stream(self):
        self.events.append(("stop_stream", self.current_scene))
        self.streaming = False


P = lambda i, s, progress=0: PrinterStatus(
    printer_id=i,
    printer_name=i,
    state=s,
    progress=progress,
    online=True,
)


def make(**kw):
    cfg = DirectorConfig(rotation_interval=1, **kw)
    pcs = [
        SimpleNamespace(id="a", obs=SimpleNamespace(scene="A")),
        SimpleNamespace(id="b", obs=SimpleNamespace(scene="B")),
    ]
    return Director(cfg, pcs, OBS())


def test_rotation_and_removal():
    async def run():
        d = make()
        d.update(P("a", PrinterState.PRINTING))
        d.update(P("b", PrinterState.PRINTING))
        await d.tick(10)
        first = d.obs.current_scene
        await d.tick(12)
        assert d.obs.current_scene != first
        d.update(P("b", PrinterState.IDLE))
        await d.tick(14)
        assert d.obs.current_scene == "A"

    asyncio.run(run())


def test_manual_return_auto():
    async def run():
        d = make()
        d.update(P("a", PrinterState.PRINTING))
        await d.command_scene("B", "b")
        await d.tick(10)
        assert d.obs.current_scene == "B"
        d.return_auto()
        await d.tick(11)
        assert d.obs.current_scene == "A"

    asyncio.run(run())


def test_stream_start_stop_grace():
    async def run():
        d = make(auto_start_stream=True, auto_stop_stream=True, stream_stop_delay=5)
        d.update(P("a", PrinterState.PRINTING))
        await d.tick(1)
        assert not d.obs.streaming
        await d.tick(2)
        assert d.obs.streaming
        d.update(P("a", PrinterState.IDLE))
        await d.tick(3)
        await d.tick(9)
        assert not d.obs.streaming

    asyncio.run(run())


def test_auto_stream_waits_for_scene_switch_and_confirmation():
    async def run():
        d = make(auto_start_stream=True)
        d.obs.current_scene = "PrintDirector Idle"
        d.update(P("a", PrinterState.PRINTING))

        await d.tick(1)

        assert d.obs.current_scene == "A"
        assert not d.obs.streaming
        assert ("start_stream", "A") not in d.obs.events

        await d.tick(2)

        assert d.obs.streaming
        set_index = d.obs.events.index(("set_scene", "A"))
        confirm_index = d.obs.events.index(("confirm_scene", "A"))
        start_index = d.obs.events.index(("start_stream", "A"))
        assert set_index < confirm_index < start_index

    asyncio.run(run())


def test_stream_start_is_blocked_if_obs_does_not_confirm_desired_scene():
    async def run():
        d = make(auto_start_stream=True)
        d.obs.current_scene = "A"
        d.update(P("a", PrinterState.PRINTING))

        async def wrong_scene():
            d.obs.events.append(("confirm_scene", "PrintDirector Idle"))
            return "PrintDirector Idle"

        d.obs.get_current_scene = wrong_scene
        await d.tick(1)

        assert not d.obs.streaming
        assert not any(event[0] == "start_stream" for event in d.obs.events)

    asyncio.run(run())


def test_stream_status_is_not_polled_when_auto_stream_control_is_disabled():
    async def run():
        d = make()
        d.update(P("a", PrinterState.PRINTING))
        await d.tick(1)
        assert d.obs.status_calls == 0

    asyncio.run(run())


def test_printer_error_beats_near_complete_event():
    d = make()
    old = P("a", PrinterState.PRINTING, 0.94)
    new = P("a", PrinterState.ERROR, 0.96)
    d._events(old, new)
    assert d.override is not None
    assert d.override.type == EventType.PRINTER_ERROR
