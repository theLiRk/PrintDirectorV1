from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class PrinterOBSConfig(BaseModel):
    scene: str


class PrinterConfig(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str
    type: Literal["klipper", "bambu"] = "klipper"
    moonraker_url: Optional[str] = None
    bambu_url: Optional[str] = None
    access_code: Optional[str] = None
    serial_number: Optional[str] = None
    stream_enabled: bool = True
    obs: PrinterOBSConfig

    @model_validator(mode="after")
    def validate_url(self):
        if self.type == "bambu":
            if not self.bambu_url and not self.moonraker_url:
                raise ValueError("Bambu printers require a bambu_url or moonraker_url")
            if not self.access_code:
                raise ValueError("Bambu printers require access_code")
            if not self.serial_number:
                raise ValueError("Bambu printers require serial_number")
            return self
        if not self.moonraker_url:
            raise ValueError("Klipper printers require moonraker_url")
        return self


class OBSConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4455
    password_env: str = "OBS_WEBSOCKET_PASSWORD"
    password: Optional[str] = None
    scene_collection: Optional[str] = None
    profile: Optional[str] = None
    reconnect_interval: float = Field(5, ge=0)
    status_poll_interval: float = Field(15, ge=1)

    # Local Windows process supervision.
    auto_launch: bool = False
    executable: Optional[str] = None
    launch_args: list[str] = Field(default_factory=list)
    process_check_interval: float = Field(5, ge=1)
    launch_cooldown: float = Field(30, ge=5)

    # Preflight and recovery. Process restart is deliberately opt-in.
    preflight_enabled: bool = True
    preflight_interval: float = Field(30, ge=5)
    startup_ready_timeout: float = Field(45, ge=5)
    reconnect_stuck_seconds: float = Field(90, ge=15)
    stream_recovery_enabled: bool = True
    stream_recovery_cooldown: float = Field(300, ge=30)
    restart_obs_on_stream_failure: bool = False
    restart_obs_cooldown: float = Field(600, ge=60)


class DirectorConfig(BaseModel):
    enabled: bool = True
    rotation_interval: float = Field(30, ge=1)
    idle_scene: str = "PrintDirector Idle"
    overview_scene: str = "Print Farm Overview"
    auto_start_stream: bool = False
    auto_stop_stream: bool = False
    stream_stop_delay: float = Field(300, ge=0)
    near_complete_threshold: float = Field(.95, ge=0, le=1)
    event_hold_times: dict[str, float] = Field(default_factory=lambda: {
        "print_started": 30,
        "print_completed": 45,
        "print_near_complete": 60,
        "printer_error": 120,
        "print_paused": 30,
    })


class MonitoringConfig(BaseModel):
    stale_after_seconds: float = Field(30, ge=5)
    stale_check_interval: float = Field(5, ge=1)
    history_limit: int = Field(100, ge=10, le=1000)


DEFAULT_NOTIFICATION_EVENTS = [
    "printer_error",
    "printer_offline",
    "print_completed",
    "telemetry_stale",
    "all_printers_unavailable",
    "obs_unavailable",
    "obs_restarted",
    "stream_recovery_failed",
]


class NotificationsConfig(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = None
    timeout: float = Field(5, ge=1, le=30)
    events: list[str] = Field(default_factory=lambda: list(DEFAULT_NOTIFICATION_EVENTS))

    @model_validator(mode="after")
    def validate_webhook(self):
        if self.enabled and not (self.webhook_url or "").strip():
            raise ValueError("notifications.webhook_url is required when notifications are enabled")
        return self


class MQTTConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    password_env: str = "PRINTDIRECTOR_MQTT_PASSWORD"
    client_id: str = "printdirector"
    topic_prefix: str = "printdirector"
    discovery_enabled: bool = True
    discovery_prefix: str = "homeassistant"
    qos: int = Field(0, ge=0, le=2)
    retain: bool = True
    keepalive: int = Field(60, ge=5, le=3600)
    heartbeat_interval: float = Field(30, ge=5)
    min_publish_interval: float = Field(2, ge=0)
    tls_enabled: bool = False
    tls_insecure: bool = False

    @model_validator(mode="after")
    def validate_mqtt(self):
        self.host = self.host.strip()
        self.topic_prefix = self.topic_prefix.strip().strip("/")
        self.discovery_prefix = self.discovery_prefix.strip().strip("/")
        self.client_id = self.client_id.strip()
        if self.enabled and not self.host:
            raise ValueError("mqtt.host is required when MQTT is enabled")
        if not self.topic_prefix or any(char in self.topic_prefix for char in "#+"):
            raise ValueError("mqtt.topic_prefix must be a normal MQTT topic without wildcards")
        if not self.discovery_prefix or any(char in self.discovery_prefix for char in "#+"):
            raise ValueError("mqtt.discovery_prefix must be a normal MQTT topic without wildcards")
        if not self.client_id:
            raise ValueError("mqtt.client_id must not be empty")
        return self


class PrinterCardConfig(BaseModel):
    accent_color: Optional[str] = None
    text_color: Optional[str] = None
    panel_opacity: Optional[float] = Field(default=None, ge=0.2, le=1.0)
    font_scale: Optional[float] = Field(default=None, ge=0.8, le=1.5)
    show_filename: Optional[bool] = None
    show_state: Optional[bool] = None
    show_eta: Optional[bool] = None
    show_temps: Optional[bool] = None
    show_layers: Optional[bool] = None
    label_override: Optional[str] = None


class OverlayThemeConfig(BaseModel):
    theme: str = "dark"
    background_color: str = "#0b0e14"
    text_color: str = "#f5f7fa"
    accent_color: str = "#38bdf8"
    panel_opacity: float = Field(0.92, ge=0.2, le=1.0)
    font_family: str = "system-ui"
    font_scale: float = Field(1.0, ge=0.8, le=1.5)
    show_filename: bool = True
    show_state: bool = True
    show_eta: bool = True
    show_temps: bool = True
    show_layers: bool = True
    printer_overrides: dict[str, PrinterCardConfig] = Field(default_factory=dict)


class AuthConfig(BaseModel):
    enabled: bool = False
    token_env: str = "PRINTDIRECTOR_TOKEN"
    token: Optional[str] = None


class OverlayConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    allow_lan: bool = False
    settings_file: str = "overlay-settings.json"
    style: OverlayThemeConfig = Field(default_factory=OverlayThemeConfig)

    @model_validator(mode="after")
    def validate_host(self):
        if self.allow_lan:
            return self
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.host not in local_hosts:
            raise ValueError(
                "Overlay host must be localhost/127.0.0.1 unless allow_lan is enabled"
            )
        return self


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: Optional[str] = "logs/printdirector.log"
    max_bytes: int = Field(10 * 1024 * 1024, ge=1024)
    backup_count: int = Field(5, ge=1, le=100)
    console: bool = True


class AppConfig(BaseModel):
    printers: list[PrinterConfig]
    obs: OBSConfig = OBSConfig()
    director: DirectorConfig = DirectorConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    mqtt: MQTTConfig = MQTTConfig()
    overlay: OverlayConfig = OverlayConfig()
    auth: AuthConfig = AuthConfig()
    logging: LoggingConfig = LoggingConfig()

    @model_validator(mode="after")
    def unique(self):
        ids = [p.id for p in self.printers]
        if len(ids) != len(set(ids)):
            raise ValueError("Printer IDs must be unique")
        return self
