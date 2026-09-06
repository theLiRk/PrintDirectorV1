import asyncio
from pathlib import Path

from .config.loader import obs_password
from .director import Director
from .obs import OBSClient
from .printers import PrinterManager


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
        self.obs = OBSClient(config.obs, obs_password(config))
        self.director = Director(config.director, config.printers, self.obs)
        for adapter in self.manager.adapters.values():
            adapter.subscribe(self.on_status)

    def on_status(self, status):
        self.director.update(status)

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
        await self.manager.start()
        self.tasks = [
            asyncio.create_task(self.director.run(), name="director"),
            asyncio.create_task(self.broadcaster(), name="broadcaster"),
        ]

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

        Uvicorn's listening host/port cannot be rebound from inside the running app;
        those values are persisted and take effect after a process restart. Printer,
        director, OBS and auth settings are rebuilt immediately.
        """
        async with self._reconfigure_lock:
            await self._stop_components()
            self.config = config
            self._build_components(config)
            await self.start()

    async def stop(self):
        async with self._reconfigure_lock:
            await self._stop_components()

    async def _stop_task(self, task):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
