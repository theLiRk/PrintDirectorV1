import asyncio
from types import SimpleNamespace

import printdirector.obs.client as client_module
from printdirector.config.models import OBSConfig
from printdirector.obs import OBSClient


class FakeWorker:
    def is_alive(self):
        return True


class FakeCallback:
    def register(self, callbacks):
        self.callbacks = callbacks


class FakeEventClient:
    def __init__(self, **kwargs):
        self.worker = FakeWorker()
        self.callback = FakeCallback()

    def disconnect(self):
        pass


def test_preflight_validates_scenes_service_collection_and_profile(monkeypatch):
    class FakeReqClient:
        def __init__(self, **kwargs):
            pass

        def get_scene_list(self):
            return SimpleNamespace(
                scenes=[{"sceneName": "Idle"}, {"sceneName": "Printer A"}],
                current_program_scene_name="Idle",
            )

        def get_scene_collection_list(self):
            return SimpleNamespace(current_scene_collection_name="PrintDirector")

        def get_profile_list(self):
            return SimpleNamespace(current_profile_name="Streaming")

        def get_stream_service_settings(self):
            return SimpleNamespace(stream_service_type="rtmp_common")

        def disconnect(self):
            pass

    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)
    monkeypatch.setattr(client_module.obs, "EventClient", FakeEventClient)

    async def run():
        client = OBSClient(
            OBSConfig(
                reconnect_interval=0,
                scene_collection="PrintDirector",
                profile="Streaming",
            ),
            "pw",
        )
        result = await client.preflight(["Idle", "Printer A"])
        assert result["ready"] is True
        assert result["missing_scenes"] == []
        assert result["scene_collection_ok"] is True
        assert result["profile_ok"] is True
        await client.close()

    asyncio.run(run())


def test_preflight_reports_missing_scene(monkeypatch):
    class FakeReqClient:
        def __init__(self, **kwargs):
            pass

        def get_scene_list(self):
            return SimpleNamespace(scenes=[{"sceneName": "Idle"}])

        def get_scene_collection_list(self):
            return SimpleNamespace(current_scene_collection_name="Default")

        def get_profile_list(self):
            return SimpleNamespace(current_profile_name="Default")

        def get_stream_service_settings(self):
            return SimpleNamespace(stream_service_type="rtmp_common")

        def disconnect(self):
            pass

    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)
    monkeypatch.setattr(client_module.obs, "EventClient", FakeEventClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        result = await client.preflight(["Idle", "Printer A"])
        assert result["ready"] is False
        assert result["missing_scenes"] == ["Printer A"]
        await client.close()

    asyncio.run(run())


def test_controlled_stream_recovery_stops_before_starting(monkeypatch):
    class FakeReqClient:
        def __init__(self, **kwargs):
            self.active = True
            self.reconnecting = True
            self.actions = []

        def get_stream_status(self):
            return SimpleNamespace(
                output_active=self.active,
                output_reconnecting=self.reconnecting,
            )

        def stop_stream(self):
            self.actions.append("stop")
            self.active = False
            self.reconnecting = False

        def start_stream(self):
            self.actions.append("start")
            self.active = True

        def disconnect(self):
            pass

    monkeypatch.setattr(client_module.obs, "ReqClient", FakeReqClient)
    monkeypatch.setattr(client_module.obs, "EventClient", FakeEventClient)

    async def run():
        client = OBSClient(OBSConfig(reconnect_interval=0), "pw")
        await client.is_streaming(force=True)
        assert client.stream_state == client.STREAM_RECONNECTING
        assert await client.recover_stream() is True
        assert client.client.actions == ["stop", "start"]
        await client.close()

    asyncio.run(run())
