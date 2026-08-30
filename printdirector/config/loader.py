import os
from pathlib import Path
import yaml
from pydantic import ValidationError
from .models import AppConfig
class ConfigurationError(RuntimeError): pass
def load_config(path:str|Path="config.yaml")->AppConfig:
 try:
  data=yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
  return AppConfig.model_validate(data)
 except FileNotFoundError as e: raise ConfigurationError(f"Configuration file not found: {path}") from e
 except (yaml.YAMLError,ValidationError) as e: raise ConfigurationError(f"Invalid configuration: {e}") from e
def obs_password(config:AppConfig)->str: return os.getenv(config.obs.password_env,"")
