import asyncio
import logging
from time import monotonic

from printdirector.models import EventType, PrinterEvent, PrinterState

log = logging.getLogger(__name__)


class Director:
    def __init__(self, config, printer_configs, obs):
        self.cfg = config
        self.obs = obs
        self.scenes = {p.id: p.obs.scene for p in printer_configs}
        self.statuses = {}
        self.previous = {}
        self.auto_enabled = config.enabled
        self.manual_scene = None
        self.current_printer = None
        self.override = None
        self.override_until = 0
        self.rotation = []
        self.index = -1
        self.last_switch = 0
        self.inactive_since = None
        self._near = set()
        self._stop = asyncio.Event()

    def update(self, status):
        old = self.previous.get(status.printer_id)
        self.statuses[status.printer_id] = status
        if old:
            self._events(old, status)
        self.previous[status.printer_id] = status.model_copy(deep=True)

    def _events(self, old, new):
        events = []
        if not old.online and new.online:
            events.append(PrinterEvent(EventType.PRINTER_ONLINE, new.printer_id))
        elif old.online and not new.online:
            events.append(PrinterEvent(EventType.PRINTER_OFFLINE, new.printer_id))
        elif new.state == PrinterState.ERROR and old.state != new.state:
            events.append(PrinterEvent(EventType.PRINTER_ERROR, new.printer_id))
        elif (
            new.state == PrinterState.PRINTING
            and old.state not in (PrinterState.PRINTING, PrinterState.PAUSED)
        ):
            events.append(PrinterEvent(EventType.PRINT_STARTED, new.printer_id))
        elif new.state == PrinterState.PAUSED and old.state != new.state:
            events.append(PrinterEvent(EventType.PRINT_PAUSED, new.printer_id))
        elif new.state == PrinterState.PRINTING and old.state == PrinterState.PAUSED:
            events.append(PrinterEvent(EventType.PRINT_RESUMED, new.printer_id))
        elif new.state == PrinterState.COMPLETE and old.state != new.state:
            events.append(PrinterEvent(EventType.PRINT_COMPLETED, new.printer_id))

        if (
            new.online
            and new.state in (PrinterState.PRINTING, PrinterState.PAUSED)
            and new.progress >= self.cfg.near_complete_threshold
            and new.printer_id not in self._near
        ):
            events.append(PrinterEvent(EventType.PRINT_NEAR_COMPLETE, new.printer_id))
            self._near.add(new.printer_id)
        if new.progress < 0.1 and new.state != PrinterState.COMPLETE:
            self._near.discard(new.printer_id)

        if events:
            self.handle_event(max(events, key=lambda event: event.priority))

    def handle_event(self, event):
        hold = self.cfg.event_hold_times.get(event.type.value, 0)
        if hold and (not self.override or event.priority >= self.override.priority):
            self.override = event
            self.override_until = monotonic() + hold

    async def command_scene(self, scene, printer=None):
        self.manual_scene = scene
        self.auto_enabled = False
        self.current_printer = printer
        await self.obs.set_scene(scene)

    def return_auto(self):
        self.manual_scene = None
        self.auto_enabled = True

    def active_ids(self):
        return sorted(
            printer_id
            for printer_id, status in self.statuses.items()
            if status.state in (PrinterState.PRINTING, PrinterState.PAUSED)
        )

    async def tick(self, now=None):
        now = now or monotonic()
        active = self.active_ids()
        if active:
            self.inactive_since = None
        elif self.inactive_since is None:
            self.inactive_since = now

        await self._stream(active, now)
        if not self.auto_enabled:
            return
        if self.override and now < self.override_until:
            await self._show(self.override.printer_id)
            return
        self.override = None
        if not active:
            await self.obs.set_scene(self.cfg.idle_scene)
            self.current_printer = None
            return
        self.rotation = active
        if len(active) == 1:
            await self._show(active[0])
            return
        if (
            now - self.last_switch >= self.cfg.rotation_interval
            or self.current_printer not in active
        ):
            self.index = (self.index + 1) % len(active)
            await self._show(active[self.index])
            self.last_switch = now

    async def _show(self, printer_id):
        scene = self.scenes.get(printer_id)
        if not scene:
            log.warning("No OBS scene configured for printer %s", printer_id)
            return
        self.current_printer = printer_id
        await self.obs.set_scene(scene)

    async def _stream(self, active, now):
        if not self.cfg.auto_start_stream and not self.cfg.auto_stop_stream:
            return

        streaming = await self.obs.is_streaming()
        if active and self.cfg.auto_start_stream and not streaming:
            await self.obs.start_stream()
        elif (
            not active
            and self.cfg.auto_stop_stream
            and streaming
            and self.inactive_since is not None
            and now - self.inactive_since >= self.cfg.stream_stop_delay
        ):
            await self.obs.stop_stream()
            self.inactive_since = now

    async def run(self):
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("Director tick failed")
            await asyncio.sleep(1)

    async def stop(self):
        self._stop.set()

    def public_status(self):
        return {
            "auto_enabled": self.auto_enabled,
            "manual_scene": self.manual_scene,
            "current_printer": self.current_printer,
            "current_event": self.override.type.value if self.override else None,
            "obs_connected": self.obs.connected,
            "obs_streaming": self.obs.streaming,
            "obs_stream_state": getattr(self.obs, "stream_state", None),
            "current_scene": self.obs.current_scene,
        }
