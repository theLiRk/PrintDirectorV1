import asyncio
from time import monotonic

import printdirector.obs.process as process_module
from printdirector.config.models import OBSConfig
from printdirector.obs.process import OBSProcessManager


def force_windows(monkeypatch):
    monkeypatch.setattr(process_module.platform, "system", lambda: "Windows")


def test_auto_launch_disabled_never_checks_or_starts(monkeypatch):
    manager = OBSProcessManager(OBSConfig(auto_launch=False))

    def fail():
        raise AssertionError("process detection should not run when auto-launch is disabled")

    monkeypatch.setattr(manager, "_is_running_sync", fail)
    assert asyncio.run(manager.ensure_running()) is False


def test_remote_obs_target_is_never_launched_locally(monkeypatch):
    force_windows(monkeypatch)
    manager = OBSProcessManager(
        OBSConfig(auto_launch=True, host="192.168.1.50")
    )

    def fail():
        raise AssertionError("remote OBS target must not trigger local process detection")

    monkeypatch.setattr(manager, "_is_running_sync", fail)
    assert asyncio.run(manager.ensure_running()) is False


def test_running_obs_is_never_launched_again(monkeypatch):
    force_windows(monkeypatch)
    manager = OBSProcessManager(OBSConfig(auto_launch=True))
    monkeypatch.setattr(manager, "_is_running_sync", lambda: True)

    def fail(_executable):
        raise AssertionError("OBS must not be launched when obs64.exe is already running")

    monkeypatch.setattr(manager, "_launch_sync", fail)
    assert asyncio.run(manager.ensure_running()) is True
    assert manager.process_running is True


def test_missing_obs_is_launched_once(monkeypatch, tmp_path):
    force_windows(monkeypatch)
    executable = tmp_path / "obs64.exe"
    executable.write_bytes(b"stub")
    manager = OBSProcessManager(
        OBSConfig(
            auto_launch=True,
            executable=str(executable),
            launch_args=["--minimize-to-tray"],
            launch_cooldown=30,
        )
    )
    monkeypatch.setattr(manager, "_is_running_sync", lambda: False)
    launched = []
    monkeypatch.setattr(manager, "_launch_sync", lambda path: launched.append(path))

    assert asyncio.run(manager.ensure_running()) is True
    assert launched == [executable.resolve()]
    assert manager.process_running is True
    assert manager.last_launch_path == str(executable.resolve())

    # tasklist can still report the old state for a moment; cooldown must prevent
    # another OBS instance while the first process is initializing.
    assert asyncio.run(manager.ensure_running()) is False
    assert len(launched) == 1


def test_process_detection_failure_never_launches(monkeypatch, tmp_path):
    force_windows(monkeypatch)
    executable = tmp_path / "obs64.exe"
    executable.write_bytes(b"stub")
    manager = OBSProcessManager(
        OBSConfig(auto_launch=True, executable=str(executable))
    )
    monkeypatch.setattr(manager, "_is_running_sync", lambda: None)
    launched = []
    monkeypatch.setattr(manager, "_launch_sync", lambda path: launched.append(path))

    assert asyncio.run(manager.ensure_running()) is False
    assert launched == []


def test_recent_launch_respects_cooldown(monkeypatch, tmp_path):
    force_windows(monkeypatch)
    executable = tmp_path / "obs64.exe"
    executable.write_bytes(b"stub")
    manager = OBSProcessManager(
        OBSConfig(auto_launch=True, executable=str(executable), launch_cooldown=30)
    )
    monkeypatch.setattr(manager, "_is_running_sync", lambda: False)
    manager.last_launch_at = monotonic()
    launched = []
    monkeypatch.setattr(manager, "_launch_sync", lambda path: launched.append(path))

    assert asyncio.run(manager.ensure_running()) is False
    assert launched == []
