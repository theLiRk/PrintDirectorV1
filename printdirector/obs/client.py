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
        self.event_client = None
        self.connected = False
        self.event_connected = False
        self.streaming = False
        self.current_scene = None
        self.stream_state = self.STREAM_UNKNOWN
        self._stream_transition_at = 0.0
        self._last_status_poll_at = 0.0
        self._next_connect_at = 0.0
        self._next_event_connect_at = 0.0
        self._event_error_reported = False
        self._lock = asyncio.Lock()
        self._stream_lock = asyncio.Lock()

    def _set_stream_state(self, state, streaming):
        old_state = self.stream_state
        old_streaming = self.streaming
        self.stream_state = state
        self.streaming = bool(streaming)
        if old_state != state or old_streaming != self.streaming:
            log.info(
                "OBS stream state %s -> %s (active=%s)",
                old_state,
                state,
                self.streaming,
            )

    def on_stream_state_changed(self, data):
        """obsws-python callback executed on the event client's worker thread."""
        output_state = str(getattr(data, "output_state", "") or "")
        active = bool(getattr(data, "output_active", False))
        mapping = {
            "OBS_WEBSOCKET_OUTPUT_STARTING": self.STREAM_STARTING,
            "OBS_WEBSOCKET_OUTPUT_STARTED": self.STREAM_STREAMING,
            "OBS_WEBSOCKET_OUTPUT_STOPPING": self.STREAM_STOPPING,
            "OBS_WEBSOCKET_OUTPUT_STOPPED": self.STREAM_STOPPED,
            "OBS_WEBSOCKET_OUTPUT_RECONNECTING": self.STREAM_RECONNECTING,
            "OBS_WEBSOCKET_OUTPUT_RECONNECTED": self.STREAM_STREAMING,
            "OBS_WEBSOCKET_OUTPUT_PAUSED": self.STREAM_STREAMING,
            "OBS_WEBSOCKET_OUTPUT_RESUMED": self.STREAM_STREAMING,
        }
        state = mapping.get(
            output_state,
            self.STREAM_STREAMING if active else self.STREAM_UNKNOWN,
        )
        if state in {self.STREAM_STARTING, self.STREAM_STOPPING}:
            self._stream_transition_at = monotonic()
        if state in {self.STREAM_STREAMING, self.STREAM_RECONNECTING}:
            active = True
        elif state == self.STREAM_STOPPED:
            active = False
        self._set_stream_state(state, active)

    def on_current_program_scene_changed(self, data):
        """Keep the scene cache in sync with manual/external OBS changes."""
        scene = getattr(data, "scene_name", None)
        if scene and scene != self.current_scene:
            self.current_scene = scene
            log.info("OBS scene event -> %s", scene)

    def _event_listener_alive(self):
        if self.event_client is None:
            return False
        worker = getattr(self.event_client, "worker", None)
        if worker is None:
            return False
        try:
            return bool(worker.is_alive())
        except Exception:
            return False

    def _create_event_client(self):
        client = obs.EventClient(
            host=self.cfg.host,
            port=self.cfg.port,
            password=self.password,
            timeout=3,
            subs=obs.Subs.OUTPUTS | obs.Subs.SCENES,
        )
        client.callback.register(
            [self.on_stream_state_changed, self.on_current_program_scene_changed]
        )
        return client

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

    async def _drop_event_client(self):
        client, self.event_client = self.event_client, None
        self.event_connected = False
        await self._disconnect_client(client)

    async def _drop_connection(self):
        request_client, self.client = self.client, None
        event_client, self.event_client = self.event_client, None
        self.connected = False
        self.event_connected = False
        self.current_scene = None
        interval = max(0.0, self.cfg.reconnect_interval)
        self._next_connect_at = monotonic() + interval
        self._next_event_connect_at = self._next_connect_at
        self._set_stream_state(self.STREAM_UNKNOWN, self.streaming)
        await asyncio.gather(
            self._disconnect_client(request_client),
            self._disconnect_client(event_client),
        )

    async def _ensure_event_client(self):
        if self._event_listener_alive():
            self.event_connected = True
            return True

        if self.event_client is not None:
            await self._drop_event_client()

        now = monotonic()
        if now < self._next_event_connect_at:
            return False
        self._next_event_connect_at = now + max(0.0, self.cfg.reconnect_interval)
        try:
            self.event_client = await asyncio.to_thread(self._create_event_client)
        except Exception as exc:
            self.event_connected = False
            if not self._event_error_reported:
                log.warning(
                    "OBS event channel unavailable; polling will be used as fallback: %s",
                    exc,
                )
                self._event_error_reported = True
            return False

        self.event_connected = True
        self._event_error_reported = False
        self._next_event_connect_at = 0.0
        log.info("OBS event channel connected")
        return True

    async def _ensure_client(self):
        if self.client is not None:
            await self._ensure_event_client()
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
        log.info("OBS request channel connected")
        await self._ensure_event_client()
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
        if ok and scene != self.current_scene:
            self.current_scene = scene
            log.info("OBS scene -> %s", scene)
        return ok

    async def get_current_scene(self):
        ok, result = await self._call("get_current_program_scene")
        if ok and result is not None:
            scene = getattr(result, "current_program_scene_name", self.current_scene)
            if scene != self.current_scene:
                self.current_scene = scene
                log.info("OBS scene status -> %s", scene)
        return self.current_scene

    def _transition_fresh(self):
        return monotonic() - self._stream_transition_at < self.STREAM_TRANSITION_TIMEOUT

    def _apply_polled_stream_status(self, result):
        active = bool(getattr(result, "output_active", False))
        reconnecting = bool(getattr(result, "output_reconnecting", False))

        if reconnecting:
            self._set_stream_state(self.STREAM_RECONNECTING, True)
        elif active:
            if self.stream_state != self.STREAM_STOPPING or not self._transition_fresh():
                self._set_stream_state(self.STREAM_STREAMING, True)
        elif (
            self.stream_state in {self.STREAM_STARTING, self.STREAM_STOPPING}
            and self._transition_fresh()
        ):
            # GetStreamStatus can report inactive while OBS is still transitioning.
            # Preserve the transition state so automation cannot race a second action.
            return
        else:
            self._set_stream_state(self.STREAM_STOPPED, False)

    async def is_streaming(self, force=False):
        event_alive = self._event_listener_alive()
        if self.event_client is not None and not event_alive:
            self.event_connected = False

        now = monotonic()
        poll_interval = max(1.0, self.cfg.status_poll_interval)
        should_poll = (
            force
            or self.stream_state == self.STREAM_UNKNOWN
            or not event_alive
            or now - self._last_status_poll_at >= poll_interval
        )
        if not should_poll:
            return self.streaming

        ok, result = await self._call("get_stream_status")
        if not ok or result is None:
            return self.streaming

        self._last_status_poll_at = monotonic()
        self._apply_polled_stream_status(result)
        return self.streaming

    async def start_stream(self):
        async with self._stream_lock:
            await self.is_streaming(force=True)
            if self.stream_state in {
                self.STREAM_STARTING,
                self.STREAM_STREAMING,
                self.STREAM_RECONNECTING,
            }:
                return False

            self._stream_transition_at = monotonic()
            self._set_stream_state(self.STREAM_STARTING, False)
            ok, _ = await self._call("start_stream")
            if not ok:
                # A request failure may mean OBS was already starting/running. Keep a
                # short transition guard until an event/watchdog poll proves otherwise.
                if not self.connected:
                    self._set_stream_state(self.STREAM_UNKNOWN, self.streaming)
                return False
            log.info("OBS stream start requested")
            return True

    async def stop_stream(self):
        async with self._stream_lock:
            await self.is_streaming(force=True)
            if self.stream_state in {self.STREAM_STOPPING, self.STREAM_STOPPED}:
                return False
            if self.stream_state == self.STREAM_STARTING and self._transition_fresh():
                log.info("OBS stream stop deferred while start is still in progress")
                return False
            if not self.streaming and self.stream_state != self.STREAM_RECONNECTING:
                return False

            self._stream_transition_at = monotonic()
            self._set_stream_state(self.STREAM_STOPPING, True)
            ok, _ = await self._call("stop_stream")
            if not ok:
                if not self.connected:
                    self._set_stream_state(self.STREAM_UNKNOWN, self.streaming)
                return False
            log.info("OBS stream stop requested")
            return True

    async def close(self):
        async with self._lock:
            request_client, self.client = self.client, None
            event_client, self.event_client = self.event_client, None
            was_connected = self.connected or self.event_connected
            self.connected = False
            self.event_connected = False
            self.current_scene = None
            self._set_stream_state(self.STREAM_UNKNOWN, False)
            self._next_connect_at = 0.0
            self._next_event_connect_at = 0.0
            self._last_status_poll_at = 0.0
            await asyncio.gather(
                self._disconnect_client(request_client),
                self._disconnect_client(event_client),
            )
            if was_connected:
                log.info("OBS websocket channels closed")
