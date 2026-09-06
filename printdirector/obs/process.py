import asyncio
import csv
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from time import monotonic

log = logging.getLogger(__name__)


class OBSProcessManager:
    DEFAULT_PROCESS_NAME = "obs64.exe"
    LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

    def __init__(self, cfg):
        self.cfg = cfg
        self.process_running = None
        self.last_launch_at = 0.0
        self.last_launch_path = None
        self.last_restart_at = 0.0
        self._unsupported_reported = False
        self._remote_target_reported = False
        self._missing_executable_reported_at = 0.0

    @property
    def supported(self):
        return platform.system().lower() == "windows"

    @property
    def local_target(self):
        return str(self.cfg.host).strip().lower() in self.LOCAL_HOSTS

    def _expand_path(self, value):
        if not value:
            return None
        return Path(os.path.expandvars(os.path.expanduser(str(value))))

    def _candidate_executables(self):
        configured = self._expand_path(self.cfg.executable)
        if configured:
            yield configured

        from_path = shutil.which(self.DEFAULT_PROCESS_NAME)
        if from_path:
            yield Path(from_path)

        seen = set()
        for base_name in ("ProgramW6432", "ProgramFiles"):
            base = os.environ.get(base_name)
            if base:
                candidate = (
                    Path(base)
                    / "obs-studio"
                    / "bin"
                    / "64bit"
                    / self.DEFAULT_PROCESS_NAME
                )
                key = str(candidate).lower()
                if key not in seen:
                    seen.add(key)
                    yield candidate

        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            yield (
                Path(program_files_x86)
                / "Steam"
                / "steamapps"
                / "common"
                / "OBS Studio"
                / "bin"
                / "64bit"
                / self.DEFAULT_PROCESS_NAME
            )

    def _resolve_executable(self):
        for candidate in self._candidate_executables():
            try:
                if candidate.is_file():
                    return candidate.resolve()
            except OSError:
                continue
        return None

    def _process_name(self):
        configured = self._expand_path(self.cfg.executable)
        if configured and configured.name:
            return configured.name
        return self.DEFAULT_PROCESS_NAME

    def _run_hidden(self, command, timeout=10):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )

    def _is_running_sync(self):
        if not self.supported:
            return None
        process_name = self._process_name()
        try:
            result = self._run_hidden(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("Unable to check whether OBS is running: %s", exc)
            return None

        if result.returncode != 0:
            log.warning(
                "tasklist failed while checking OBS (exit %s): %s",
                result.returncode,
                (result.stderr or "").strip(),
            )
            return None

        wanted = process_name.lower()
        try:
            rows = csv.reader(result.stdout.splitlines())
            return any(row and row[0].strip().lower() == wanted for row in rows)
        except csv.Error:
            return None

    async def is_running(self):
        running = await asyncio.to_thread(self._is_running_sync)
        if running is not None and running != self.process_running:
            log.info("OBS process %s", "detected" if running else "not running")
        self.process_running = running
        return running

    def _launch_sync(self, executable):
        command = [str(executable), *list(self.cfg.launch_args)]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            command,
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )

    def _terminate_sync(self):
        process_name = self._process_name()
        result = self._run_hidden(["taskkill", "/IM", process_name, "/T", "/F"], timeout=10)
        return result.returncode in {0, 128}

    async def ensure_running(self):
        if not self.cfg.auto_launch:
            return False
        if not self.local_target:
            if not self._remote_target_reported:
                log.warning(
                    "OBS auto-launch is disabled because obs.host points to a remote host: %s",
                    self.cfg.host,
                )
                self._remote_target_reported = True
            return False
        if not self.supported:
            if not self._unsupported_reported:
                log.warning("OBS auto-launch is currently supported on Windows only")
                self._unsupported_reported = True
            return False

        running = await self.is_running()
        if running is True:
            return True
        if running is None:
            return False

        now = monotonic()
        cooldown = max(5.0, self.cfg.launch_cooldown)
        if now - self.last_launch_at < cooldown:
            return False

        executable = self._resolve_executable()
        if executable is None:
            if now - self._missing_executable_reported_at >= cooldown:
                log.error(
                    "OBS auto-launch is enabled but obs64.exe could not be found. "
                    "Set obs.executable to the full OBS executable path."
                )
                self._missing_executable_reported_at = now
            return False

        self.last_launch_at = now
        self.last_launch_path = str(executable)
        try:
            await asyncio.to_thread(self._launch_sync, executable)
        except Exception as exc:
            log.exception("Failed to launch OBS from %s: %s", executable, exc)
            return False

        self.process_running = True
        log.info("OBS launch requested: %s", executable)
        return True

    async def restart(self):
        """Restart local OBS. Caller must enforce the configured recovery policy."""
        if not self.cfg.auto_launch or not self.local_target or not self.supported:
            return False
        now = monotonic()
        if now - self.last_restart_at < max(60.0, self.cfg.restart_obs_cooldown):
            return False
        running = await self.is_running()
        if running is None:
            return False
        self.last_restart_at = now
        if running:
            log.warning("Restarting OBS after failed stream recovery")
            try:
                terminated = await asyncio.to_thread(self._terminate_sync)
            except Exception as exc:
                log.exception("Unable to terminate OBS for recovery: %s", exc)
                return False
            if not terminated:
                return False
            for _ in range(20):
                await asyncio.sleep(0.5)
                running = await self.is_running()
                if running is False:
                    break
            if running is not False:
                log.error("OBS did not exit during recovery restart")
                return False

        self.last_launch_at = 0.0
        self.process_running = False
        return await self.ensure_running()
