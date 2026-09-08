import asyncio
import logging
from time import monotonic

from printdirector.models import EventType, PrinterEvent, PrinterState

log = logging.getLogger(__name__)


class Director:
    STREAM_SCENE_SETTLE_SECONDS = 1.0

    def __init__(self, config, printer_configs, obs, event_sink=None):
        self.cfg = config
        self.obs = obs
        self.event_sink = event_sink
        self.scenes = {p.id: p.obs.scene for p in printer_configs}
        self.stream_enabled_ids = {
            p.id for p in printer_configs if getattr(p, "stream_enabled", True)
        }
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
        self._stream_scene_candidate = None
        self._stream_scene_candidate_since = 0.0

    def update(self, status):
        old = self.previous.get(status.printer_id)
        self.statuses[status.printer_id] = status
        if old is None:
            log.info(
                "Printer %s initial state: %s (online=%s stale=%s)",
                status.printer_id,
                status.state.value,
                status.online,
                getattr(status, "stale", False),
            )
        else:
            if (
                old.online != status.online
                or old.state != status.state
                or getattr(old, "stale", False) != getattr(status, "stale", False)
            ):
                log.info(
                    "Printer %s state %s/%s -> %s/%s%s",
                    status.printer_id,
                    old.state.value,
                    "online" if old.online else "offline",
                    status.state.value,
                    "online" if status.online else "offline",
                    "/stale" if getattr(status, "stale", False) else "",
                )
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
            and not getattr(new, "stale", False)
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
        if self.event_sink:
            try:
                self.event_sink(event)
            except Exception:
                log.exception("Director event sink failed")

        # Excluding a printer from automatic streaming must not suppress its
        # telemetry/events. It only prevents Director from forcing that
        # printer's scene as an automatic event override.
        if event.printer_id not in self.stream_enabled_ids:
            return

        hold = self.cfg.event_hold_times.get(event.type.value, 0)
        if hold and (not self.override or event.priority >= self.override.priority):
            self.override = event
            self.override_until = monotonic() + hold
            log.info(
                "Director event %s for %s; scene override for %.0fs",
                event.type.value,
                event.printer_id,
                hold,
            )

    async def command_scene(self, scene, printer=None):
        self.manual_scene = scene
        self.auto_enabled = False
        self.current_printer = printer
        log.info("Director manual scene: %s", scene)
        await self.obs.set_scene(scene)

    def return_auto(self):
        self.manual_scene = None
        self.auto_enabled = True
        log.info("Director returned to automatic mode")

    def active_ids(self):
        return sorted(
            printer_id
            for printer_id, status in self.statuses.items()
            if printer_id in self.stream_enabled_ids
            and status.online
            and not getattr(status, "stale", False)
            and status.state in (PrinterState.PRINTING, PrinterState.PAUSED)
        )

    def desired_scene(self, now=None):
        now = now or monotonic()
        if not self.auto_enabled and self.manual_scene:
            return self.manual_scene
        if self.override and now < self.override_until:
            return self.scenes.get(self.override.printer_id)
        active = self.active_ids()
        if not active:
            return self.cfg.idle_scene
        if self.current_printer in active:
            return self.scenes.get(self.current_printer)
        if len(active) > 1 and self.cfg.overview_scene:
            return self.cfg.overview_scene
        return self.scenes.get(active[0])

    async def restore_scene(self):
        scene = self.desired_scene()
        if not scene:
            return False
        log.info("Restoring intended OBS scene after reconnect: %s", scene)
        return await self.obs.set_scene(scene)

    async def tick(self, now=None):
        now = now or monotonic()
        active = self.active_ids()
        if active:
            self.inactive_since = None
        elif self.inactive_since is None:
            self.inactive_since = now

        # Manual mode still keeps automatic stream start/stop behavior, but the
        # scene was already selected by command_scene before we get here.
        if not self.auto_enabled:
            await self._stream(active, now)
            return

        # In automatic mode, always select the intended scene before touching
        # the stream output. Starting the stream while OBS is still on the old
        # scene can leave OBS visually rendering the old composition even after
        # CurrentProgramScene has advanced to the new scene.
        scene_changed = False
        if self.override and now < self.override_until:
            scene_changed = await self._show(self.override.printer_id)
        else:
            self.override = None
            if not active:
                previous_scene = self.obs.current_scene
                ok = await self.obs.set_scene(self.cfg.idle_scene)
                scene_changed = previous_scene != self.cfg.idle_scene and ok is not False
                self.current_printer = None
            else:
                self.rotation = active
                if len(active) == 1:
                    scene_changed = await self._show(active[0])
                elif (
                    now - self.last_switch >= self.cfg.rotation_interval
                    or self.current_printer not in active
                ):
                    self.index = (self.index + 1) % len(active)
                    scene_changed = await self._show(active[self.index])
                    self.last_switch = now

        await self._stream(active, now, defer_start=scene_changed)

    async def _show(self, printer_id):
        scene = self.scenes.get(printer_id)
        if not scene:
            log.warning("No OBS scene configured for printer %s", printer_id)
            return False
        previous_scene = self.obs.current_scene
        self.current_printer = printer_id
        ok = await self.obs.set_scene(scene)
        return previous_scene != scene and ok is not False

    def _reset_stream_scene_candidate(self):
        self._stream_scene_candidate = None
        self._stream_scene_candidate_since = 0.0

    async def _stream(self, active, now, defer_start=False):
        if not self.cfg.auto_start_stream and not self.cfg.auto_stop_stream:
            self._reset_stream_scene_candidate()
            return

        streaming = await self.obs.is_streaming()
        if active and self.cfg.auto_start_stream and not streaming:
            desired = self.desired_scene(now)

            if defer_start:
                self._stream_scene_candidate = desired
                self._stream_scene_candidate_since = now
                log.info(
                    "OBS stream start deferred for %.1fs while Program scene settles",
                    self.STREAM_SCENE_SETTLE_SECONDS,
                )
                return

            if desired:
                get_current_scene = getattr(self.obs, "get_current_scene", None)
                if callable(get_current_scene):
                    current = await get_current_scene()
                else:
                    current = self.obs.current_scene
                if current != desired:
                    self._reset_stream_scene_candidate()
                    log.warning(
                        "OBS stream start deferred until Program scene is confirmed as %s (current=%s)",
                        desired,
                        current,
                    )
                    return

                # A scene may have been changed by the startup/reconnect watchdog
                # rather than by Director.tick(). Treat the first successful
                # confirmation as the beginning of the settle period so every
                # automatic stream start gets the same protection.
                if self._stream_scene_candidate != desired:
                    self._stream_scene_candidate = desired
                    self._stream_scene_candidate_since = now
                    log.info(
                        "OBS Program scene %s confirmed; waiting %.1fs before stream start",
                        desired,
                        self.STREAM_SCENE_SETTLE_SECONDS,
                    )
                    return

                stable_for = max(0.0, now - self._stream_scene_candidate_since)
                if stable_for < self.STREAM_SCENE_SETTLE_SECONDS:
                    log.info(
                        "OBS stream start deferred; Program scene %s has been stable for %.1fs",
                        desired,
                        stable_for,
                    )
                    return

            await self.obs.start_stream()
            self._reset_stream_scene_candidate()
        elif (
            not active
            and self.cfg.auto_stop_stream
            and streaming
            and self.inactive_since is not None
            and now - self.inactive_since >= self.cfg.stream_stop_delay
        ):
            self._reset_stream_scene_candidate()
            await self.obs.stop_stream()
            self.inactive_since = now
        elif streaming or not active:
            self._reset_stream_scene_candidate()

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
            "obs_events_connected": getattr(self.obs, "event_connected", False),
            "obs_streaming": self.obs.streaming,
            "obs_stream_state": getattr(self.obs, "stream_state", None),
            "obs_stream_state_age": getattr(self.obs, "stream_state_age", 0),
            "obs_preflight": getattr(self.obs, "last_preflight", None),
            "current_scene": self.obs.current_scene,
        }
