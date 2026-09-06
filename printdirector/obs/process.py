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
    """Detect and optionally launch OBS without creating duplicate instances.

    Automatic process management is intentionally Windows-only for now because
    PrintDirector's production deployment runs on Windows and process discovery can
    be made deterministic there with tasklist. Other platforms keep the existing
    manual-start behavior even if auto_launch is accidentally enabled.
    """

    DEFAULT_PROCESS_NAME = "obs64.exe"
    LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

    def __init__(self, cfg):
        self.cfg = cfg
        self.process_running = None
        self.last_launch_at = 0.0
        self.last_launch_path = None
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

    def _is_running_sync(self):
        if not self.supported:
            return None
        process_name = self._process_name()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"IMAGENAME eq {process_name}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=creationflags,
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
            # If process detection itself failed, never risk starting a duplicate OBS.
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

        # Treat the process as tentatively running until the next tasklist check. The
        # cooldown prevents another launch while OBS is still initializing.
        self.process_running = True
        log.info("OBS launch requested: %s", executable)
        return True
