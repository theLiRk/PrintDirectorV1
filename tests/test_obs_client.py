import asyncio
from types import SimpleNamespace

import printdirector.obs.client as client_module
from printdirector.config.models import OBSConfig
from printdirector.obs import OBSClient


class FakeWorker:
    def __init__(self):
        self.alive = True

    def is_alive(self):
        return self.alive


class FakeCallback:
    def __init__(self):
        self.registered = []

    def register(self, callbacks):
        if isinstance(callbacks, (list, tuple)):
            self.registered.extend(callbacks)
        else:
            self.registered.append(callbacks)


class FakeEventClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.callback = FakeCallback()
        self.worker = FakeWorker()
        self.disconnected = False
        self.__class__.instances.append(self)

    def disconnect(self):
        self.disconnected = True
        self.worker.alive = False


def patch_event_client(monkeypatch):
    FakeEventClient.instances.clear()
    monkeypatch.setattr(client_module.obs, "EventClient", FakeEventClient)


def test_start_stream_is_not_duplicated_while_obs_is_starting(monkeypatch):
    class FakeReqClient:
        instances = []

        def __init__(self, **kwargs):
            self.start_calls = 0
            self.disconnected = False
            self.__class__.instances.append(self)

        def get_stream_status(self):
            # Mirrors the state visible in the crash log: OBS can still report
            # inactive while the RTMP output is starting.
            return SimpleNamespace(output_active=False, output_reconnecting=False)

        def start_stream(self):
            self.start_calls += 1

        def disconnect(self):
            self.disconnected = True

    patch_event_client(monkeypatch)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        assert await client.start_stream() is True
        assert client.stream_state == client.STREAM_STARTING
        assert await client.start_stream() is False
        assert FakeReqClient.instances[0].start_calls == 1
        assert client.event_connected is True
        await client.close()
        assert FakeReqClient.instances[0].disconnected is True
        assert FakeEventClient.instances[0].disconnected is True

    asyncio.run(run())


def test_obs_request_error_does_not_drop_healthy_websocket(monkeypatch):
    class RequestRejected(Exception):
        code = 601

    class FakeReqClient:
        def __init__(self, **kwargs):
            self.disconnected = False

        def set_current_program_scene(self, scene):
            raise RequestRejected("scene does not exist")

        def disconnect(self):
            self.disconnected = True

    patch_event_client(monkeypatch)
    monkeypatch.setattr(client_module, "OBSSDKRequestError", RequestRejected)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        assert await client.set_scene("missing") is False
        assert client.connected is True
        assert client.client is not None
        assert client.client.disconnected is False
        assert client.event_connected is True
        await client.close()

    asyncio.run(run())


def test_transport_error_disconnects_both_channels_and_respects_backoff(monkeypatch):
    class FakeReqClient:
        instances = []

        def __init__(self, **kwargs):
            self.disconnected = False
            self.__class__.instances.append(self)

        def get_current_program_scene(self):
            raise OSError("socket gone")

        def disconnect(self):
            self.disconnected = True

    patch_event_client(monkeypatch)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=5), "pw")
        assert await client.get_current_scene() is None
        assert client.connected is False
        assert client.event_connected is False
        assert client.client is None
        assert client.event_client is None
        assert FakeReqClient.instances[0].disconnected is True
        assert FakeEventClient.instances[0].disconnected is True

        # An immediate second request must not create another websocket client.
        assert await client.get_current_scene() is None
        assert len(FakeReqClient.instances) == 1

    asyncio.run(run())


def test_stream_events_are_primary_with_polling_as_watchdog(monkeypatch):
    class FakeReqClient:
        def __init__(self, **kwargs):
            self.status_calls = 0

        def get_stream_status(self):
            self.status_calls += 1
            return SimpleNamespace(output_active=False, output_reconnecting=False)

        def disconnect(self):
            pass

    patch_event_client(monkeypatch)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(
            OBSConfig(reconnect_interval=0, status_poll_interval=30), "pw"
        )
        assert await client.is_streaming(force=True) is False
        assert client.client.status_calls == 1

        client.on_stream_state_changed(
            SimpleNamespace(
                output_state="OBS_WEBSOCKET_OUTPUT_STARTED", output_active=True
            )
        )
        assert client.streaming is True
        assert client.stream_state == client.STREAM_STREAMING

        # Healthy events mean no second GetStreamStatus until the watchdog interval.
        assert await client.is_streaming() is True
        assert client.client.status_calls == 1
        await client.close()

    asyncio.run(run())


def test_obs_events_update_stream_and_scene_cache():
    client = OBSClient(OBSConfig(), "pw")

    client.on_stream_state_changed(
        SimpleNamespace(
            output_state="OBS_WEBSOCKET_OUTPUT_RECONNECTING", output_active=True
        )
    )
    assert client.streaming is True
    assert client.stream_state == client.STREAM_RECONNECTING

    client.on_current_program_scene_changed(SimpleNamespace(scene_name="Printer - Jötunn"))
    assert client.current_scene == "Printer - Jötunn"

    client.on_stream_state_changed(
        SimpleNamespace(
            output_state="OBS_WEBSOCKET_OUTPUT_STOPPED", output_active=False
        )
    )
    assert client.streaming is False
    assert client.stream_state == client.STREAM_STOPPED


def test_event_channel_failure_falls_back_to_polling(monkeypatch):
    class FailingEventClient:
        def __init__(self, **kwargs):
            raise OSError("events unavailable")

    class FakeReqClient:
        def __init__(self, **kwargs):
            self.status_calls = 0

        def get_stream_status(self):
            self.status_calls += 1
            return SimpleNamespace(output_active=True, output_reconnecting=False)

        def disconnect(self):
            pass

    monkeypatch.setattr(client_module.obs, "EventClient", FailingEventClient)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        assert await client.is_streaming() is True
        assert client.connected is True
        assert client.event_connected is False
        assert client.client.status_calls == 1
        await client.close()

    asyncio.run(run())
