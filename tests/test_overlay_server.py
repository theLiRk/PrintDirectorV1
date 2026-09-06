import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from printdirector.config.models import AppConfig
from printdirector.overlay.server import Hub, create_app


class FakeSocket:
    def __init__(self, delay=0):
        self.delay = delay
        self.sent = []

    async def send_json(self, data):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(data)


class FakeOBS:
    def __init__(self, connect_on_poll=True):
        self.connected = False
        self.event_connected = False
        self.stream_state = "unknown"
        self.streaming = False
        self.current_scene = None
        self.connect_on_poll = connect_on_poll
        self.polls = []

    async def is_streaming(self, force=False):
        self.polls.append(force)
        if self.connect_on_poll:
            self.connected = True
        return self.streaming


class FakeRuntime:
    def __init__(self, tmp_path, running=True, connect_on_poll=True):
        self.config = AppConfig.model_validate(
            {
                "printers": [
                    {
                        "id": "a",
                        "name": "A",
                        "moonraker_url": "http://x",
                        "obs": {"scene": "A"},
                    }
                ]
            }
        )
        self.config_path = tmp_path / "config.yaml"
        self.demo = False
        self._running = running
        self.obs = FakeOBS(connect_on_poll=connect_on_poll)
        self.manager = SimpleNamespace(
            statuses=lambda: {"a": SimpleNamespace(online=True)},
            adapters={"a": object()},
        )
        self.director = SimpleNamespace(
            public_status=lambda: {
                "auto_enabled": True,
                "obs_connected": self.obs.connected,
            },
            scenes={"a": "A"},
        )
        self.hub = None

    def is_running(self):
        return self._running


def test_hub_slow_client_does_not_block_other_clients():
    async def run():
        hub = Hub(send_timeout=0.02)
        fast = FakeSocket()
        slow = FakeSocket(delay=0.2)
        hub.clients.update({fast, slow})

        await hub.broadcast({"hello": "world"})

        assert fast.sent == [{"hello": "world"}]
        assert fast in hub.clients
        assert slow not in hub.clients

    asyncio.run(run())


def test_health_is_liveness_and_ready_performs_obs_watchdog(tmp_path):
    runtime = FakeRuntime(tmp_path)
    client = TestClient(create_app(runtime))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert runtime.obs.polls == []

    ready = client.get("/api/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert runtime.obs.polls == [True]
    assert ready.json()["obs_connected"] is True


def test_ready_returns_503_when_obs_cannot_connect(tmp_path):
    runtime = FakeRuntime(tmp_path, connect_on_poll=False)
    client = TestClient(create_app(runtime))

    ready = client.get("/api/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "degraded"
