import asyncio
from types import SimpleNamespace

import printdirector.obs.client as client_module
from printdirector.config.models import OBSConfig
from printdirector.obs import OBSClient


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

    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        assert await client.start_stream() is True
        assert client.stream_state == client.STREAM_STARTING
        assert await client.start_stream() is False
        assert FakeReqClient.instances[0].start_calls == 1
        await client.close()
        assert FakeReqClient.instances[0].disconnected is True

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

    monkeypatch.setattr(client_module, "OBSSDKRequestError", RequestRejected)
    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        assert await client.set_scene("missing") is False
        assert client.connected is True
        assert client.client is not None
        assert client.client.disconnected is False
        await client.close()

    asyncio.run(run())


def test_transport_error_disconnects_and_respects_reconnect_backoff(monkeypatch):
    class FakeReqClient:
        instances = []

        def __init__(self, **kwargs):
            self.disconnected = False
            self.__class__.instances.append(self)

        def get_current_program_scene(self):
            raise OSError("socket gone")

        def disconnect(self):
            self.disconnected = True

    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=5), "pw")
        assert await client.get_current_scene() is None
        assert client.connected is False
        assert client.client is None
        assert FakeReqClient.instances[0].disconnected is True

        # An immediate second request must not create another websocket client.
        assert await client.get_current_scene() is None
        assert len(FakeReqClient.instances) == 1

    asyncio.run(run())
