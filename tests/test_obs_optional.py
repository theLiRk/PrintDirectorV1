import asyncio

from printdirector.config.models import AppConfig, OBSConfig
from printdirector.obs import OBSClient, OBSProcessManager


def test_obs_enabled_defaults_true_for_existing_configs():
    config = AppConfig.model_validate(
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
    assert config.obs.enabled is True


def test_obs_can_be_disabled_for_mqtt_only_operation():
    config = AppConfig.model_validate(
        {
            "printers": [
                {
                    "id": "a",
                    "name": "A",
                    "moonraker_url": "http://x",
                    "obs": {"scene": "A"},
                }
            ],
            "obs": {"enabled": False, "auto_launch": True},
            "mqtt": {"enabled": True, "host": "mqtt.local"},
        }
    )
    assert config.obs.enabled is False
    assert config.mqtt.enabled is True


def test_disabled_obs_client_never_creates_real_client_and_all_actions_are_noops():
    async def run():
        client = OBSClient(OBSConfig(enabled=False), "secret")
        assert client._client is None
        assert client.connected is False
        assert client.event_connected is False
        assert client.stream_state == "disabled"
        assert await client.is_streaming(force=True) is False
        assert await client.set_scene("Printer - A") is False
        assert await client.start_stream() is False
        assert await client.stop_stream() is False
        assert await client.recover_stream() is False
        preflight = await client.preflight(["Printer - A"])
        assert preflight["ready"] is True
        assert preflight["disabled"] is True
        assert preflight["connected"] is False
        await client.close()

    asyncio.run(run())


def test_disabled_obs_process_manager_never_checks_or_launches_obs():
    async def run():
        manager = OBSProcessManager(OBSConfig(enabled=False, auto_launch=True))
        assert manager._manager is None
        assert await manager.is_running() is None
        assert await manager.ensure_running() is False
        assert await manager.restart() is False

    asyncio.run(run())
