from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"
ENV_PREFIX = "AWSBREAKER_"


def load_file(path: Path) -> dict[str, Any]:
    """Load YAML, TOML, or JSON config file."""
    if not path.exists():
        return {}
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(path.read_text()) or {}
    if suffix == ".toml":
        return tomllib.loads(path.read_text()) or {}
    if suffix == ".json":
        return json.loads(path.read_text()) or {}
    raise ValueError(f"Unsupported config format: {suffix}")


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """Recursively update mapping dst with src (in place) and return dst."""
    for key, value in src.items():
        if key in dst and isinstance(dst[key], dict) and isinstance(value, dict):
            _deep_update(dst[key], value)
        else:
            dst[key] = value
    return dst


def _load_env(prefix: str = ENV_PREFIX) -> dict[str, Any]:
    """Load env vars with PREFIX_ into nested dict. Types inferred via YAML parser.

    Example: AWSBREAKER_AWS__REGION=us-west-2 => {"aws": {"region": "us-west-2"}}
    """
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        # Strip prefix and support nesting with double underscore
        path = key[len(prefix) :].lower()
        parts = path.split("__")
        cur = result
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        # Use YAML to coerce string to bool/int/float/list/dict when possible
        try:
            parsed: Any = yaml.safe_load(value)
        except Exception:
            parsed = value
        cur[parts[-1]] = parsed
    return result


class Config:
    """A thin wrapper around a dict to provide dot-access for nested keys."""

    def __init__(self, data: dict[str, Any]):
        self._data = {k: self._wrap(v) for k, v in data.items()}

    @classmethod
    def _wrap(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return Config(value)
        if isinstance(value, list):
            return [cls._wrap(v) for v in value]
        return value

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def to_dict(self) -> dict[str, Any]:
        def unwrap(v: Any) -> Any:
            if isinstance(v, Config):
                return {k: unwrap(val) for k, val in v._data.items()}
            if isinstance(v, list):
                return [unwrap(i) for i in v]
            return v

        return {k: unwrap(v) for k, v in self._data.items()}


_settings: Config | None = None


def get_config(cli_args: dict | None = None, config_file: Path | None = None) -> Config:
    """Merge defaults, files, env vars, and CLI args into a singleton Config."""
    global _settings
    if _settings is not None:
        return _settings

    # 1) Defaults from bundled YAML
    merged: dict[str, Any] = load_file(DEFAULT_CONFIG_PATH)

    # 2) Home overrides (~/.awsbreaker.{yaml,yml,toml,json})
    for ext in ("yaml", "yml", "toml", "json"):
        home_file = Path.home() / f".awsbreaker.{ext}"
        if home_file.exists():
            _deep_update(merged, load_file(home_file))

    # 3) Explicit config file
    if config_file:
        _deep_update(merged, load_file(config_file))

    # 4) Environment variables
    env_overrides = _load_env()
    if env_overrides:
        _deep_update(merged, env_overrides)

    # 5) CLI overrides
    if cli_args:
        _deep_update(merged, {k: v for k, v in cli_args.items() if v is not None})

    _settings = Config(merged)
    return _settings


def reload_config(**kwargs) -> Config:
    global _settings
    _settings = None
    return get_config(**kwargs)
