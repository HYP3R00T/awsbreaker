from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from awsbreaker.conf.config import (
    Config,
    _deep_update,
    _load_env,
    get_config,
    load_file,
    reload_config,
)


def test_load_file_missing_returns_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "missing.yaml"
    assert not p.exists()
    assert load_file(p) == {}


def test_load_file_unsupported_extension_raises(tmp_path: Path) -> None:
    p = tmp_path / "cfg.ini"
    p.write_text("k=v")
    with pytest.raises(ValueError):
        load_file(p)


def test_load_file_reads_yaml_json_toml(tmp_path: Path) -> None:
    # YAML
    yaml_p = tmp_path / "a.yaml"
    yaml_p.write_text(yaml.safe_dump({"a": 1, "b": {"c": True}}))
    assert load_file(yaml_p) == {"a": 1, "b": {"c": True}}

    # JSON
    json_p = tmp_path / "b.json"
    json_p.write_text(json.dumps({"x": [1, 2, 3]}))
    assert load_file(json_p) == {"x": [1, 2, 3]}

    # TOML
    toml_p = tmp_path / "c.toml"
    toml_p.write_text("""foo = 1
[bar]
baz = true
""")
    got = load_file(toml_p)
    assert got["foo"] == 1
    assert got["bar"]["baz"] is True


def test_deep_update_recursive_merge() -> None:
    dst = {"a": 1, "b": {"x": 10, "y": 20}, "c": {"k": 1}}
    src = {"b": {"y": 99, "z": 42}, "c": 2, "d": 3}
    out = _deep_update(dst, src)
    assert out == {"a": 1, "b": {"x": 10, "y": 99, "z": 42}, "c": 2, "d": 3}


def test_load_env_parses_types_and_nesting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWSBREAKER_FOO__BAR", "true")
    monkeypatch.setenv("AWSBREAKER_NUM", "123")
    monkeypatch.setenv("AWSBREAKER_LIST", "[1, 2, 3]")

    data = _load_env()
    assert data == {"foo": {"bar": True}, "num": 123, "list": [1, 2, 3]}


def test_config_wrapper_access_and_to_dict() -> None:
    cfg = Config({"api_url": "x", "aws": {"region": "r"}, "list": [{"a": 1}]})
    assert cfg.api_url == "x"
    assert cfg.aws.region == "r"
    assert cfg["api_url"] == "x"
    assert cfg.to_dict() == {"api_url": "x", "aws": {"region": "r"}, "list": [{"a": 1}]}
    with pytest.raises(AttributeError):
        _ = cfg.missing


def test_singleton_and_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    # Initial config from env
    monkeypatch.setenv("AWSBREAKER_TIMEOUT", "7")
    cfg1 = get_config()
    assert cfg1.timeout == 7

    # Change env; cached singleton should not change until reload
    monkeypatch.setenv("AWSBREAKER_TIMEOUT", "8")
    cfg2 = get_config()
    assert cfg2 is cfg1
    assert cfg2.timeout == 7

    # After reload, new value should be reflected
    reload_config()
    cfg3 = get_config()
    assert cfg3.timeout == 8


def test_load_env_safe_load_exception_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force yaml.safe_load to raise so we hit the exception branch and fallback to raw string
    monkeypatch.setenv("AWSBREAKER_BROKEN", "{not: yaml}")
    import awsbreaker.conf.config as cfgmod

    def boom(_value: str):  # type: ignore[no-untyped-def]
        raise ValueError("parse error")

    monkeypatch.setattr(cfgmod.yaml, "safe_load", boom)
    data = _load_env()
    assert data == {"broken": "{not: yaml}"}


def test_get_config_with_explicit_file_and_cli_args(tmp_path: Path) -> None:
    # Prepare a specific config file to exercise the explicit file branch
    cfg_file = tmp_path / "overrides.yaml"
    cfg_file.write_text(
        yaml.safe_dump({
            "api_url": "https://from-file",
            "timeout": 99,
            "nested": {"x": 1},
        })
    )

    # Pass CLI args including a None to ensure None-valued keys are filtered
    cli_args = {"debug": True, "retries": None, "nested": {"y": 2}}

    # Ensure fresh singleton and load with both explicit file and CLI args
    cfg = reload_config(config_file=cfg_file, cli_args=cli_args)

    # From file
    assert cfg.api_url == "https://from-file"
    assert cfg.timeout == 99
    assert cfg.nested.x == 1

    # From CLI (merge and None filtered)
    assert cfg.debug is True  # overridden by CLI
    # 'retries' does not exist in defaults and None-valued CLI keys are ignored
    with pytest.raises(AttributeError):
        _ = cfg.retries
    assert cfg.nested.y == 2  # merged into nested dict
