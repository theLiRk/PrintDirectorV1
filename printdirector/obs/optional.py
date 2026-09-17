from datetime import datetime, timezone

from .client import OBSClient as _OBSClient
from .process import OBSProcessManager as _OBSProcessManager


class OBSClient:
    """OBS client facade that becomes a network-free no-op when OBS is disabled."""

    STREAM_UNKNOWN = _OBSClient.STREAM_UNKNOWN
    STREAM_STOPPED = _OBSClient.STREAM_STOPPED
    STREAM_STARTING = _OBSClient.STREAM_STARTING
    STREAM_STREAMING = _OBSClient.STREAM_STREAMING
    STREAM_RECONNECTING = _OBSClient.STREAM_RECONNECTING
    STREAM_STOPPING = _OBSClient.STREAM_STOPPING
    STREAM_DISABLED = "disabled"

    def __init__(self, cfg, password):
        self.cfg = cfg
        self.enabled = bool(getattr(cfg, "enabled", True))
        self._client = _OBSClient(cfg, password) if self.enabled else None
        if not self.enabled:
            self.connected = False
            self.event_connected = False
            self.streaming = False
            self.current_scene = None
            self.stream_state = self.STREAM_DISABLED
            self.last_preflight = self._disabled_preflight()

    def __getattr__(self, name):
        if self._client is not None:
            return getattr(self._client, name)
        raise AttributeError(name)

    @property
    def stream_state_age(self):
        if self._client is not None:
            return self._client.stream_state_age
        return 0.0

    def _disabled_preflight(self):
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ready": True,
            "connected": False,
            "disabled": True,
            "scenes_ok": True,
            "missing_scenes": [],
            "stream_service_configured": False,
            "stream_service_type": None,
            "current_scene": None,
            "scene_collection": None,
            "scene_collection_ok": True,
            "profile": None,
            "profile_ok": True,
        }

    async def set_scene(self, scene):
        if self._client is not None:
            return await self._client.set_scene(scene)
        return False

    async def get_current_scene(self):
        if self._client is not None:
            return await self._client.get_current_scene()
        return None

    async def ensure_environment(self):
        if self._client is not None:
            return await self._client.ensure_environment()
        return False

    async def preflight(self, required_scenes=None):
        if self._client is not None:
            return await self._client.preflight(required_scenes)
        self.last_preflight = self._disabled_preflight()
        return self.last_preflight

    async def is_streaming(self, force=False):
        if self._client is not None:
            return await self._client.is_streaming(force=force)
        return False

    async def start_stream(self):
        if self._client is not None:
            return await self._client.start_stream()
        return False

    async def stop_stream(self):
        if self._client is not None:
            return await self._client.stop_stream()
        return False

    async def recover_stream(self):
        if self._client is not None:
            return await self._client.recover_stream()
        return False

    async def close(self):
        if self._client is not None:
            return await self._client.close()
        return None


class OBSProcessManager:
    """Process manager facade that never probes, launches, or restarts OBS when disabled."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = bool(getattr(cfg, "enabled", True))
        self._manager = _OBSProcessManager(cfg) if self.enabled else None
        if not self.enabled:
            self.process_running = None
            self.last_launch_at = 0.0
            self.last_launch_path = None
            self.last_restart_at = 0.0

    def __getattr__(self, name):
        if self._manager is not None:
            return getattr(self._manager, name)
        raise AttributeError(name)

    async def is_running(self):
        if self._manager is not None:
            return await self._manager.is_running()
        return None

    async def ensure_running(self):
        if self._manager is not None:
            return await self._manager.ensure_running()
        return False

    async def restart(self):
        if self._manager is not None:
            return await self._manager.restart()
        return False
