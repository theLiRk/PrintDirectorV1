import os
from pathlib import Path
from typing import Any, Union

import yaml
from pydantic import ValidationError

from .models import AppConfig

class ConfigurationError(RuntimeError): pass


def _merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
 merged = dict(base)
 for key, value in updates.items():
   if isinstance(value, dict) and isinstance(merged.get(key), dict):
     merged[key] = _merge_dicts(merged[key], value)
   else:
     merged[key] = value
 return merged


def load_config(path:Union[str, Path] = "config.yaml") -> AppConfig:
 config_path = Path(path)
 overrides_path = config_path.with_suffix('.local.json')
 try:
  data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
  if overrides_path.exists():
   try:
     overrides = __import__('json').loads(overrides_path.read_text(encoding='utf-8')) or {}
     if isinstance(overrides, dict):
       data = _merge_dicts(data, overrides)
   except Exception:
     pass
  return AppConfig.model_validate(data)
 except FileNotFoundError as e: raise ConfigurationError(f"Configuration file not found: {path}") from e
 except (yaml.YAMLError, ValidationError) as e: raise ConfigurationError(f"Invalid configuration: {e}") from e


def obs_password(config: AppConfig) -> str:
 if config.obs.password:
   return config.obs.password
 return os.getenv(config.obs.password_env, "")
