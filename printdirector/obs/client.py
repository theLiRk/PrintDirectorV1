import asyncio
import logging
from time import monotonic

import obsws_python as obs
from obsws_python.error import OBSSDKRequestError

log = logging.getLogger(__name__)


class OBSClient:
    STREAM_UNKNOWN = "unknown"
    STREAM_STOPPED = "stopped"
    STREAM_STARTING = "starting"
    STREAM_STREAMING = "streaming"
    STREAM_RECONNECTING = "reconnecting"
    STREAM_STOPPING = "stopping"
    STREAM_TRANSITION_TIMEOUT = 15.0

    def __init__(self, cfg, password):
        self.cfg = cfg
        self.password = password
        self.client = None
        self.connected = False
        self.streaming = False
        self.current_scene = None
        self.stream_state = self.STREAM_UNKNOWN
        self._stream_transition_at = 0.0
        self._next_connect_at = 0.0
        self._lock = asyncio.Lock()
        self._stream_lock = asyncio.Lock()

    async def _disconnect_client(self, client):
        if client is None:
            return
        try:
            disconnect = getattr(client, "disconnect", None)
            if disconnect:
                await asyncio.to_thread(disconnect)
                return
            exit_method = getattr(client, "__exit__", None)
            if exit_method:
                await asyncio.to_thread(exit_method, None, None, None)
        except Exception as exc:
            log.debug("OBS websocket cleanup failed: %s", exc)

    async def _drop_connection(self):
        client, self.client = self.client, None
        self.connected = False
        self.current_scene = None
        self._next_connect_at = monotonic() + max(0.0, self.cfg.reconnect_interval)
        await self._disconnect_client(client)

    async def _ensure_client(self):
        if self.client is not None:
            return True
        now = monotonic()
        if now < self._next_connect_at:
            return False
        self._next_connect_at = now + max(0.0, self.cfg.reconnect_interval)
        try:
            self.client = await asyncio.to_thread(
                obs.ReqClient,
                host=self.cfg.host,
                port=self.cfg.port,
                password=self.password,
                timeout=3,
            )
        except Exception as exc:
            self.connected = False
            log.warning("OBS unavailable: %s", exc)
            return False
        self.connected = True
        self.current_scene = None
        self._next_connect_at = 0.0
        log.info("OBS connected")
        return True

    async def _call(self, name, *args):
        async with self._lock:
            if not await self._ensure_client():
                return False, None
            try:
                result = await asyncio.to_thread(getattr(self.client, name), *args)
                return True, result
            except OBSSDKRequestError as exc:
                # OBS rejected the request, but the websocket itself is still healthy.
                log.warning(
                    "OBS request %s rejected (code %s): %s",
                    name,
                    getattr(exc, "code", "unknown"),
                    exc,
                )
                return False, None
            except Exception as exc:
                log.warning("OBS connection lost during %s: %s", name, exc)
                await self._drop_connection()
                return False, None

    async def set_scene(self, scene):
        if scene == self.current_scene and self.connected:
            return True
        ok, _ = await self._call("set_current_program_scene", scene)
        if ok:
            self.current_scene = scene
            log.info("OBS scene -> %s", scene)
        return ok

    async def get_current_scene(self):
        ok, result = await self._call("get_current_program_scene")
        if ok and result is not None:
            self.current_scene = getattr(
                result, "current_program_scene_name", self.current_scene
            )
        return self.current_scene

    def _transition_fresh(self):
        return monotonic() - self._stream_transition_at < self.STREAM_TRANSITION_TIMEOUT

    async def is_streaming(self):
        ok, result = await self._call("get_stream_status")
        if not ok or result is None:
            return self.streaming

        active = bool(getattr(result, "output_active", False))
        reconnecting = bool(getattr(result, "output_reconnecting", False))

        if reconnecting:
            self.streaming = True
            self.stream_state = self.STREAM_RECONNECTING
        elif active:
            self.streaming = True
            if self.stream_state != self.STREAM_STOPPING or not self._transition_fresh():
                self.stream_state = self.STREAM_STREAMING
        elif self.stream_state == self.STREAM_STARTING and self._transition_fresh():
            # OBS can report inactive while the RTMP output is still starting. Do not
            # allow a second StartStream request during this window.
            self.streaming = False
        else:
            self.streaming = False
            self.stream_state = self.STREAM_STOPPED
        return self.streaming

    async def start_stream(self):
        async with self._stream_lock:
            await self.is_streaming()
            if self.stream_state in {
                self.STREAM_STARTING,
                self.STREAM_STREAMING,
                self.STREAM_RECONNECTING,
            }:
                return False

            self.stream_state = self.STREAM_STARTING
            self._stream_transition_at = monotonic()
            ok, _ = await self._call("start_stream")
            if not ok:
                # A request failure may mean OBS was already starting/running. Keep a
                # short transition guard until status can prove otherwise.
                if not self.connected:
                    self.stream_state = self.STREAM_UNKNOWN
                return False
            log.info("OBS stream start requested")
            return True

    async def stop_stream(self):
        async with self._stream_lock:
            await self.is_streaming()
            if self.stream_state in {self.STREAM_STOPPING, self.STREAM_STOPPED}:
                return False
            if self.stream_state == self.STREAM_STARTING and self._transition_fresh():
                log.info("OBS stream stop deferred while start is still in progress")
                return False
            if not self.streaming and self.stream_state != self.STREAM_RECONNECTING:
                return False

            self.stream_state = self.STREAM_STOPPING
            self._stream_transition_at = monotonic()
            ok, _ = await self._call("stop_stream")
            if not ok:
                if not self.connected:
                    self.stream_state = self.STREAM_UNKNOWN
                return False
            log.info("OBS stream stop requested")
            return True

    async def close(self):
        async with self._lock:
            client, self.client = self.client, None
            self.connected = False
            self.current_scene = None
            self.streaming = False
            self.stream_state = self.STREAM_UNKNOWN
            self._next_connect_at = 0.0
            await self._disconnect_client(client)
