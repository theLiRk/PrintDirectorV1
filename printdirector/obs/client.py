import asyncio
import logging
from datetime import datetime, timezone
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
        self.stream_state_changed_at = monotonic()
        self.last_preflight = None
        self._stream_transition_at = 0.0
        self._last_status_poll_at = 0.0
        self._next_connect_at = 0.0
        self._next_event_connect_at = 0.0
        self._event_error_reported = False
        self._lock = asyncio.Lock()
        self._stream_lock = asyncio.Lock()
        self._recovery_lock = asyncio.Lock()

    @property
    def stream_state_age(self):
        return max(0.0, monotonic() - self.stream_state_changed_at)

    def _set_stream_state(self, state, streaming):
        old_state = self.stream_state
        old_streaming = self.streaming
        self.stream_state = state
        self.streaming = bool(streaming)
        if old_state != state:
            self.stream_state_changed_at = monotonic()
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

    async def ensure_environment(self):
        """Optionally enforce the configured OBS scene collection and profile."""
        changed = False
        if self.cfg.scene_collection:
            ok, result = await self._call("get_scene_collection_list")
            current = getattr(result, "current_scene_collection_name", None) if ok and result is not None else None
            if current and current != self.cfg.scene_collection:
                switched, _ = await self._call("set_current_scene_collection", self.cfg.scene_collection)
                if not switched:
                    return False
                changed = True
                self.current_scene = None
                log.info("OBS scene collection -> %s", self.cfg.scene_collection)
        if self.cfg.profile:
            ok, result = await self._call("get_profile_list")
            current = getattr(result, "current_profile_name", None) if ok and result is not None else None
            if current and current != self.cfg.profile:
                switched, _ = await self._call("set_current_profile", self.cfg.profile)
                if not switched:
                    return False
                changed = True
                log.info("OBS profile -> %s", self.cfg.profile)
        if changed:
            await asyncio.sleep(1)
        return True

    @staticmethod
    def _scene_name(item):
        if isinstance(item, dict):
            return item.get("sceneName") or item.get("scene_name") or item.get("name")
        return (
            getattr(item, "scene_name", None)
            or getattr(item, "sceneName", None)
            or getattr(item, "name", None)
        )

    async def preflight(self, required_scenes=None):
        required = [scene for scene in (required_scenes or []) if scene]
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ready": False,
            "connected": False,
            "scenes_ok": False,
            "missing_scenes": list(required),
            "stream_service_configured": False,
            "stream_service_type": None,
            "current_scene": self.current_scene,
            "scene_collection": None,
            "scene_collection_ok": not bool(self.cfg.scene_collection),
            "profile": None,
            "profile_ok": not bool(self.cfg.profile),
        }

        ok, scene_result = await self._call("get_scene_list")
        if not ok or scene_result is None:
            self.last_preflight = result
            return result

        scenes = {
            name
            for name in (self._scene_name(item) for item in (getattr(scene_result, "scenes", None) or []))
            if name
        }
        missing = [scene for scene in required if scene not in scenes]
        result["connected"] = True
        result["missing_scenes"] = missing
        result["scenes_ok"] = not missing
        current = getattr(scene_result, "current_program_scene_name", None)
        if current:
            self.current_scene = current
            result["current_scene"] = current

        collection_ok, collection_result = await self._call("get_scene_collection_list")
        if collection_ok and collection_result is not None:
            current_collection = getattr(collection_result, "current_scene_collection_name", None)
            result["scene_collection"] = current_collection
            result["scene_collection_ok"] = (
                not self.cfg.scene_collection or current_collection == self.cfg.scene_collection
            )

        profile_ok, profile_result = await self._call("get_profile_list")
        if profile_ok and profile_result is not None:
            current_profile = getattr(profile_result, "current_profile_name", None)
            result["profile"] = current_profile
            result["profile_ok"] = not self.cfg.profile or current_profile == self.cfg.profile

        service_ok, service_result = await self._call("get_stream_service_settings")
        if service_ok and service_result is not None:
            service_type = (
                getattr(service_result, "stream_service_type", None)
                or getattr(service_result, "streamServiceType", None)
            )
            result["stream_service_type"] = service_type
            result["stream_service_configured"] = bool(service_type)

        result["ready"] = bool(
            result["connected"]
            and result["scenes_ok"]
            and result["stream_service_configured"]
            and result["scene_collection_ok"]
            and result["profile_ok"]
        )
        self.last_preflight = result
        return result

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

    async def recover_stream(self):
        """Perform one controlled stop/start cycle for a stuck active output."""
        async with self._recovery_lock:
            await self.is_streaming(force=True)
            if self.stream_state not in {self.STREAM_RECONNECTING, self.STREAM_STREAMING}:
                return False
            log.warning("Attempting controlled OBS stream recovery")
            if not await self.stop_stream():
                return False

            stopped = False
            for _ in range(8):
                await asyncio.sleep(1)
                ok, status = await self._call("get_stream_status")
                if not ok or status is None:
                    return False
                if not bool(getattr(status, "output_active", False)):
                    self._set_stream_state(self.STREAM_STOPPED, False)
                    stopped = True
                    break
            if not stopped:
                log.warning("OBS stream did not stop during recovery")
                return False

            started = await self.start_stream()
            if not started and self.stream_state not in {
                self.STREAM_STARTING,
                self.STREAM_STREAMING,
                self.STREAM_RECONNECTING,
            }:
                return False
            return True

    async def close(self):
        async with self._lock:
            request_client, self.client = self.client, None
            event_client, self.event_client = self.event_client, None
            was_connected = self.connected or self.event_connected
            self.connected = False
            self.event_connected = False
            self.current_scene = None
            self.last_preflight = None
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
