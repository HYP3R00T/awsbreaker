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
