import asyncio
import logging
from pathlib import Path

from .config.loader import obs_password
from .director import Director
from .obs import OBSClient, OBSProcessManager
from .printers import PrinterManager

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, config, demo=False, config_path="config.yaml"):
        self.config = config
        self.demo = demo
        self.config_path = Path(config_path)
        self.hub = None
        self.tasks = []
        self._reconfigure_lock = asyncio.Lock()
        self._build_components(config)

    def _build_components(self, config):
        self.manager = PrinterManager(config.printers, self.demo)
        self.obs_process = OBSProcessManager(config.obs)
        self.obs = OBSClient(config.obs, obs_password(config))
        self.director = Director(config.director, config.printers, self.obs)
        for adapter in self.manager.adapters.values():
            adapter.subscribe(self.on_status)

    def on_status(self, status):
        self.director.update(status)

    def is_running(self):
        return bool(self.tasks) and all(not task.done() for task in self.tasks)

    async def obs_watchdog(self):
        intervals = [
            max(self.config.obs.reconnect_interval, 1.0),
            self.config.obs.status_poll_interval,
        ]
        if self.config.obs.auto_launch:
            intervals.append(self.config.obs.process_check_interval)
        interval = max(1.0, min(intervals))

        while True:
            try:
                if not self.demo and self.config.obs.auto_launch:
                    await self.obs_process.ensure_running()
                await self.obs.is_streaming()
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
        ]
        log.info("PrintDirector runtime started")

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
        """Apply runtime-safe configuration changes without leaving stale components.

        Uvicorn's listening host/port and the process logging handlers cannot be
        rebound safely from inside the running request. Those values are persisted
        and reported as requiring a restart. Printer, director, OBS and auth settings
        are rebuilt immediately.
        """
        async with self._reconfigure_lock:
            log.info("Reconfiguring PrintDirector runtime")
            await self._stop_components()
            self.config = config
            self._build_components(config)
            await self.start()

    async def stop(self):
        async with self._reconfigure_lock:
            await self._stop_components()
            log.info("PrintDirector runtime stopped")

    async def _stop_task(self, task):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
