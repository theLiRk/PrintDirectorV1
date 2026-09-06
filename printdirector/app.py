import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .config.loader import obs_password
from .director import Director
from .models import EventType
from .obs import OBSClient, OBSProcessManager
from .printers import PrinterManager
from .utils.events import EventHistory
from .utils.notifications import WebhookNotifier

log = logging.getLogger(__name__)


EVENT_SEVERITY = {
    EventType.PRINTER_ERROR.value: "error",
    EventType.PRINTER_OFFLINE.value: "warning",
    EventType.PRINT_PAUSED.value: "warning",
}


class Runtime:
    def __init__(self, config, demo=False, config_path="config.yaml"):
        self.config = config
        self.demo = demo
        self.config_path = Path(config_path)
        self.hub = None
        self.tasks = []
        self.history = EventHistory(config.monitoring.history_limit)
        self.notifier = WebhookNotifier(config.notifications)
        self._reconfigure_lock = asyncio.Lock()
        self._last_preflight_at = 0.0
        self._last_stream_recovery_at = 0.0
        self._obs_connected_previous = None
        self._preflight_ready_previous = None
        self._seen_printers = set()
        self._all_printers_unavailable = False
        self._build_components(config)

    def _build_components(self, config):
        self.manager = PrinterManager(config.printers, self.demo)
        self.obs_process = OBSProcessManager(config.obs)
        self.obs = OBSClient(config.obs, obs_password(config))
        self.director = Director(
            config.director,
            config.printers,
            self.obs,
            event_sink=self.on_director_event,
        )
        self.notifier = WebhookNotifier(config.notifications)
        self.history.resize(config.monitoring.history_limit)
        self._last_preflight_at = 0.0
        self._last_stream_recovery_at = 0.0
        self._obs_connected_previous = None
        self._preflight_ready_previous = None
        self._seen_printers.clear()
        self._all_printers_unavailable = False
        for adapter in self.manager.adapters.values():
            adapter.subscribe(self.on_status)

    def record_event(self, event_type, message, severity="info", printer_id=None, details=None):
        item = self.history.add(event_type, message, severity, printer_id, details)
        log_method = log.error if severity == "error" else log.warning if severity == "warning" else log.info
        log_method("Event %s: %s", event_type, message)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return item
        if self.notifier.should_send(item):
            loop.create_task(self.notifier.send(item), name=f"notify-{event_type}")
        return item

    def on_director_event(self, event):
        status = self.manager.statuses().get(event.printer_id)
        name = status.printer_name if status else event.printer_id
        label = event.type.value.replace("_", " ")
        self.record_event(
            event.type.value,
            f"{name}: {label}",
            EVENT_SEVERITY.get(event.type.value, "info"),
            event.printer_id,
        )

    def on_status(self, status):
        adapter = self.manager.adapters.get(status.printer_id)
        was_stale = bool(getattr(status, "stale", False))
        if was_stale:
            status = status.model_copy(update={"stale": False})
            if adapter is not None:
                adapter.status = status
            self.record_event(
                "telemetry_recovered",
                f"{status.printer_name}: telemetry resumed",
                printer_id=status.printer_id,
            )
        self._seen_printers.add(status.printer_id)
        self.director.update(status)
        self._check_all_printers_unavailable()

    def _check_all_printers_unavailable(self):
        statuses = self.manager.statuses()
        if not statuses or self._seen_printers != set(statuses):
            return
        unavailable = all((not status.online) or getattr(status, "stale", False) for status in statuses.values())
        if unavailable and not self._all_printers_unavailable:
            self._all_printers_unavailable = True
            self.record_event(
                "all_printers_unavailable",
                "All configured printers are offline or stale",
                "error",
            )
        elif not unavailable and self._all_printers_unavailable:
            self._all_printers_unavailable = False
            self.record_event("printer_connectivity_recovered", "Printer connectivity recovered")

    def is_running(self):
        return bool(self.tasks) and all(not task.done() for task in self.tasks)

    def required_scenes(self):
        scenes = [self.config.director.idle_scene, self.config.director.overview_scene]
        scenes.extend(self.director.scenes.values())
        return list(dict.fromkeys(scene for scene in scenes if scene))

    def operational_status(self):
        statuses = self.manager.statuses()
        stale = [status.printer_id for status in statuses.values() if getattr(status, "stale", False)]
        return {
            "runtime_running": self.is_running(),
            "obs_connected": self.obs.connected,
            "obs_events_connected": self.obs.event_connected,
            "obs_stream_state": self.obs.stream_state,
            "obs_stream_state_age": round(self.obs.stream_state_age, 1),
            "obs_preflight": self.obs.last_preflight,
            "obs_process_running": self.obs_process.process_running,
            "configured_printers": len(statuses),
            "online_printers": sum(status.online and not getattr(status, "stale", False) for status in statuses.values()),
            "stale_printers": stale,
            "notifications_enabled": self.config.notifications.enabled,
        }

    async def stale_watchdog(self):
        while True:
            try:
                now = datetime.now(timezone.utc)
                threshold = self.config.monitoring.stale_after_seconds
                for printer_id, adapter in self.manager.adapters.items():
                    status = adapter.status
                    if not status.online or getattr(status, "stale", False):
                        continue
                    last_update = status.last_update
                    if last_update.tzinfo is None:
                        last_update = last_update.replace(tzinfo=timezone.utc)
                    age = (now - last_update).total_seconds()
                    if age < threshold:
                        continue
                    stale_status = status.model_copy(update={"stale": True})
                    adapter.status = stale_status
                    self.director.update(stale_status)
                    self.record_event(
                        "telemetry_stale",
                        f"{status.printer_name}: no telemetry for {age:.0f}s",
                        "warning",
                        printer_id,
                        {"age_seconds": round(age, 1)},
                    )
                self._check_all_printers_unavailable()
            except Exception:
                log.exception("Printer stale watchdog failed")
            await asyncio.sleep(self.config.monitoring.stale_check_interval)

    async def _run_preflight(self, force=False):
        if not self.config.obs.preflight_enabled:
            return None
        now = monotonic()
        if not force and now - self._last_preflight_at < self.config.obs.preflight_interval:
            return self.obs.last_preflight
        self._last_preflight_at = now
        result = await self.obs.preflight(self.required_scenes())
        ready = bool(result.get("ready"))
        if ready != self._preflight_ready_previous:
            if ready:
                self.record_event("obs_ready", "OBS preflight passed")
            elif result.get("connected"):
                reasons = []
                missing = ", ".join(result.get("missing_scenes") or [])
                if missing:
                    reasons.append(f"missing scenes: {missing}")
                if not result.get("stream_service_configured"):
                    reasons.append("stream service is not configured")
                if not result.get("scene_collection_ok", True):
                    reasons.append(f"scene collection is {result.get('scene_collection') or '--'}")
                if not result.get("profile_ok", True):
                    reasons.append(f"profile is {result.get('profile') or '--'}")
                reason = "; ".join(reasons) or "unknown preflight failure"
                self.record_event("obs_preflight_failed", f"OBS preflight failed: {reason}", "warning", details=result)
            self._preflight_ready_previous = ready
        return result

    async def _restore_after_obs_connection(self):
        await self.obs.ensure_environment()
        preflight = await self._run_preflight(force=True)
        if not preflight or not preflight.get("connected"):
            return False
        if preflight.get("scenes_ok"):
            await self.director.restore_scene()
        return bool(preflight.get("ready"))

    async def _wait_for_obs_ready(self):
        deadline = monotonic() + self.config.obs.startup_ready_timeout
        environment_applied = False
        while monotonic() < deadline:
            if self.obs.connected and not environment_applied:
                environment_applied = await self.obs.ensure_environment()
            preflight = await self._run_preflight(force=True)
            if preflight and preflight.get("ready"):
                return True
            await asyncio.sleep(2)
        return False

    async def _recover_stuck_stream(self):
        cfg = self.config.obs
        if self.obs.stream_state != self.obs.STREAM_RECONNECTING:
            return
        if self.obs.stream_state_age < cfg.reconnect_stuck_seconds:
            return
        now = monotonic()
        if now - self._last_stream_recovery_at < cfg.stream_recovery_cooldown:
            return
        self._last_stream_recovery_at = now

        self.record_event(
            "stream_recovery_started",
            f"OBS has been reconnecting for {self.obs.stream_state_age:.0f}s; attempting recovery",
            "warning",
        )
        recovered = False
        if cfg.stream_recovery_enabled:
            recovered = await self.obs.recover_stream()
        if recovered:
            self.record_event("stream_recovery_requested", "Controlled OBS stream restart requested")
            return

        self.record_event("stream_recovery_failed", "Controlled OBS stream recovery failed", "error")
        if not cfg.restart_obs_on_stream_failure:
            return

        should_resume_stream = self.obs.streaming or self.obs.stream_state == self.obs.STREAM_RECONNECTING
        await self.obs.close()
        restarted = await self.obs_process.restart()
        if not restarted:
            self.record_event("obs_restart_failed", "OBS process restart failed or was blocked by cooldown", "error")
            return

        self.record_event("obs_restarted", "OBS process restarted after stream recovery failure", "warning")
        if not await self._wait_for_obs_ready():
            self.record_event("obs_restart_not_ready", "OBS restarted but did not pass preflight in time", "error")
            return
        await self.director.restore_scene()
        if should_resume_stream:
            await self.obs.start_stream()

    async def obs_watchdog(self):
        intervals = [
            max(self.config.obs.reconnect_interval, 1.0),
            self.config.obs.status_poll_interval,
            self.config.obs.preflight_interval,
        ]
        if self.config.obs.auto_launch:
            intervals.append(self.config.obs.process_check_interval)
        interval = max(1.0, min(intervals))

        while True:
            try:
                launch_before = self.obs_process.last_launch_at
                if not self.demo and self.config.obs.auto_launch:
                    await self.obs_process.ensure_running()
                    if self.obs_process.last_launch_at != launch_before:
                        self.record_event("obs_launched", "OBS was not running and was launched", "warning")

                await self.obs.is_streaming()
                connected = self.obs.connected
                if connected != self._obs_connected_previous:
                    if connected:
                        self.record_event("obs_connected", "OBS WebSocket connected")
                        await self._restore_after_obs_connection()
                    elif self._obs_connected_previous is True:
                        self.record_event("obs_unavailable", "OBS WebSocket connection lost", "warning")
                    self._obs_connected_previous = connected

                if connected:
                    await self._run_preflight()
                    await self._recover_stuck_stream()
            except Exception:
                log.exception("OBS watchdog failed")
            await asyncio.sleep(interval)

    async def broadcaster(self):
        while True:
            if self.hub:
                await self.hub.broadcast(
                    {
                        "printers": [
                            status.model_dump(mode="json")
                            for status in self.manager.statuses().values()
                        ],
                        "director": self.director.public_status(),
                        "operations": self.operational_status(),
                        "events": self.history.list(20),
                    }
                )
            await asyncio.sleep(1)

    async def start(self):
        if not self.demo and self.config.obs.auto_launch:
            await self.obs_process.ensure_running()
        await self.manager.start()
        self.tasks = [
            asyncio.create_task(self.director.run(), name="director"),
            asyncio.create_task(self.broadcaster(), name="broadcaster"),
            asyncio.create_task(self.obs_watchdog(), name="obs-watchdog"),
            asyncio.create_task(self.stale_watchdog(), name="stale-watchdog"),
        ]
        self.record_event("runtime_started", "PrintDirector runtime started")

    async def _stop_components(self):
        cleanup = asyncio.gather(
            self.director.stop(),
            self.manager.stop(),
            *(self._stop_task(task) for task in self.tasks),
        )
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
        self.tasks.clear()
        await self.obs.close()

    async def reconfigure(self, config):
        async with self._reconfigure_lock:
            log.info("Reconfiguring PrintDirector runtime")
            await self._stop_components()
            self.config = config
            self._build_components(config)
            await self.start()

    async def stop(self):
        async with self._reconfigure_lock:
            await self._stop_components()
            self.record_event("runtime_stopped", "PrintDirector runtime stopped")

    async def _stop_task(self, task):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
