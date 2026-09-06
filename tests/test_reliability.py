from types import SimpleNamespace

import pytest

from printdirector.config.models import AppConfig, DirectorConfig, NotificationsConfig
from printdirector.director import Director
from printdirector.models import PrinterState, PrinterStatus
from printdirector.utils.diagnostics import redact
from printdirector.utils.events import EventHistory


def make_config(**extra):
    data = {
        "printers": [
            {"id": "a", "name": "A", "moonraker_url": "http://x", "obs": {"scene": "A"}}
        ]
    }
    data.update(extra)
    return AppConfig.model_validate(data)


def test_reliability_defaults_are_conservative():
    cfg = make_config()
    assert cfg.obs.preflight_enabled is True
    assert cfg.obs.stream_recovery_enabled is True
    assert cfg.obs.restart_obs_on_stream_failure is False
    assert cfg.monitoring.stale_after_seconds == 30
    assert cfg.monitoring.history_limit == 100
    assert cfg.notifications.enabled is False


def test_notifications_require_url_when_enabled():
    with pytest.raises(ValueError):
        NotificationsConfig(enabled=True)


def test_event_history_is_bounded_and_newest_first():
    history = EventHistory(10)
    for i in range(12):
        history.add(f"e{i}", str(i))
    items = history.list()
    assert len(items) == 10
    assert items[0]["type"] == "e11"
    assert items[-1]["type"] == "e2"


def test_redaction_removes_runtime_secrets():
    data = redact({"obs": {"password": "pw"}, "printer": {"access_code": "1234"}, "safe": "x"})
    assert data["obs"]["password"] == "***REDACTED***"
    assert data["printer"]["access_code"] == "***REDACTED***"
    assert data["safe"] == "x"


def test_stale_printer_is_removed_from_director_rotation():
    class OBS:
        connected = True
        event_connected = True
        streaming = False
        current_scene = None
        stream_state = "stopped"
        stream_state_age = 0
        last_preflight = None

        async def set_scene(self, scene):
            self.current_scene = scene
            return True

    director = Director(
        DirectorConfig(),
        [SimpleNamespace(id="a", obs=SimpleNamespace(scene="A"))],
        OBS(),
    )
    fresh = PrinterStatus(
        printer_id="a", printer_name="A", state=PrinterState.PRINTING, online=True
    )
    director.update(fresh)
    assert director.active_ids() == ["a"]
    director.update(fresh.model_copy(update={"stale": True}))
    assert director.active_ids() == []
    assert director.desired_scene() == "PrintDirector Idle"
