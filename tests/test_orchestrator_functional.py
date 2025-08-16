import logging
from types import SimpleNamespace
from typing import Any

import pytest

import awsbreaker.orchestrator as orch


def test_functional_entrypoint_success_and_progress(monkeypatch, caplog):
    # Configure single service and region
    cfg = SimpleNamespace(aws=SimpleNamespace(services=["funcsvc"], region=["us-east-1"]))

    class FakeSession:
        def get_available_regions(self, service_name: str):  # noqa: D401, ARG002
            return ["us-east-1"]

    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    monkeypatch.setattr(orch, "create_aws_session", lambda _cfg: FakeSession())

    # Functional handler returns deletion count and uses reporter
    def handler(session: Any, region: str, dry_run: bool, reporter):  # noqa: D401, ARG001
        reporter({
            "phase": "plan",
            "resource_type": "thing",
            "id": "x",
            "name": "n",
            "action": "delete",
            "status": "ok",
            "reason": "policy",
            "extra": {"k": "v"},
        })
        assert region == "us-east-1"
        assert dry_run is False
        return 3

    # Patch service map
    orig = orch.SERVICE_HANDLERS.copy()
    orch.SERVICE_HANDLERS.clear()
    orch.SERVICE_HANDLERS["funcsvc"] = handler

    progress_calls: list[dict[str, int]] = []

    with caplog.at_level(logging.INFO, logger=orch.__name__):
        summary = orch.orchestrate_services(dry_run=False, progress_cb=lambda s: progress_calls.append(dict(s)))

    # Restore service map
    orch.SERVICE_HANDLERS.clear()
    orch.SERVICE_HANDLERS.update(orig)

    assert summary == {"submitted": 1, "skipped": 0, "failures": 0, "succeeded": 1, "deletions": 3}
    # Ensure our reporter logged something
    assert any("[funcsvc]" in rec.message for rec in caplog.records)
    # Progress should be called at least initial and final
    assert progress_calls[0]["pending"] >= 0
    assert progress_calls[-1]["completed"] == 1


def test_no_valid_services_config_raises(monkeypatch):
    cfg = SimpleNamespace(aws=SimpleNamespace(services=["unknown"], region=["us-east-1"]))
    monkeypatch.setattr(orch, "get_config", lambda: cfg)

    with pytest.raises(ValueError, match="No valid services selected"):
        orch.orchestrate_services()


def test_no_regions_config_raises(monkeypatch):
    cfg = SimpleNamespace(aws=SimpleNamespace(services=["ec2"], region=[]))
    monkeypatch.setattr(orch, "get_config", lambda: cfg)

    with pytest.raises(ValueError, match="No regions configured under aws.region"):
        orch.orchestrate_services()


def test_all_regions_union_empty_raises(monkeypatch):
    cfg = SimpleNamespace(aws=SimpleNamespace(services=["funcsvc"], region=["all"]))

    class FakeSession:
        def get_available_regions(self, service_name: str):  # noqa: D401, ARG002
            return []

    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    monkeypatch.setattr(orch, "create_aws_session", lambda _cfg: FakeSession())

    # Provide at least one handler to avoid previous error
    orig = orch.SERVICE_HANDLERS.copy()
    orch.SERVICE_HANDLERS.clear()

    def handler(session: Any, region: str, dry_run: bool, reporter):  # noqa: D401, ARG001
        return 0

    orch.SERVICE_HANDLERS["funcsvc"] = handler

    try:
        with pytest.raises(ValueError, match="Unable to resolve regions for selected services"):
            orch.orchestrate_services()
    finally:
        orch.SERVICE_HANDLERS.clear()
        orch.SERVICE_HANDLERS.update(orig)


def test_unsupported_handler_type_counts_failure(monkeypatch):
    cfg = SimpleNamespace(aws=SimpleNamespace(services=["weird"], region=["us-east-1"]))

    class FakeSession:
        def get_available_regions(self, service_name: str):  # noqa: D401, ARG002
            return ["us-east-1"]

    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    monkeypatch.setattr(orch, "create_aws_session", lambda _cfg: FakeSession())

    orig = orch.SERVICE_HANDLERS.copy()
    orch.SERVICE_HANDLERS.clear()
    # Use an object that is not a function or class but has a __name__ attribute
    handler_obj = type("WeirdObj", (), {})()
    handler_obj.__name__ = "weird_handler"  # type: ignore[attr-defined]
    orch.SERVICE_HANDLERS["weird"] = handler_obj  # unsupported type to trigger TypeError in worker

    try:
        summary = orch.orchestrate_services(dry_run=True)
        assert summary["failures"] == 1
        assert summary["submitted"] == 1
    finally:
        orch.SERVICE_HANDLERS.clear()
        orch.SERVICE_HANDLERS.update(orig)
