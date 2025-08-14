import logging
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

import awsbreaker.orchestrator as orch


class DummyHandler:
    """A fake service handler to exercise orchestrator logic.

    Records calls to scan_resources/delete_resources and can be configured
    to raise from scan to test failure paths.
    """

    # These are set per-instance by orchestrator
    def __init__(self, session: Any, region: str, dry_run: bool):
        self.session = session
        self.region = region
        self.dry_run = dry_run

    def scan_resources(self):
        # Allow test to control behavior via session-provided switch
        behavior = getattr(self.session, "behavior", {})
        if behavior.get("raise_on_scan") and self.region == behavior.get("raise_region"):
            raise RuntimeError("scan failed")
        return behavior.get("resources", {}).get(self.region, [])

    def delete_resources(self, resources):
        # record deletes for assertions
        rec = getattr(self.session, "deleted", [])
        rec.append((self.region, len(resources)))
        self.session.deleted = rec


@contextmanager
def patched_services(monkeypatch: pytest.MonkeyPatch, service_key: str, handler: Any):
    # Patch the service registry to include our dummy handler
    orig_map = orch.SERVICE_HANDLERS.copy()
    try:
        orch.SERVICE_HANDLERS.clear()
        orch.SERVICE_HANDLERS[service_key] = handler
        yield
    finally:
        orch.SERVICE_HANDLERS.clear()
        orch.SERVICE_HANDLERS.update(orig_map)


def make_config(services, regions, max_workers: int | None = None):
    aws_ns = SimpleNamespace(services=services, region=regions)
    if max_workers is not None:
        aws_ns.max_workers = max_workers
    cfg = SimpleNamespace(aws=aws_ns)
    return cfg


def test_orchestrate_skips_unsupported_regions(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    # Config asks for regions including one unsupported; dynamic map will only allow us-east-1
    cfg = make_config(["dummy"], ["us-east-1", "eu-west-1"])  # eu-west-1 will be skipped

    class FakeSession:
        def get_available_regions(self, service_name: str):  # noqa: D401
            return ["us-east-1"]

    # Patch config and session creation
    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    monkeypatch.setattr(orch, "create_aws_session", lambda _cfg: FakeSession())

    # Patch handler map
    with patched_services(monkeypatch, "dummy", DummyHandler), caplog.at_level(logging.INFO, logger=orch.__name__):
        orch.orchestrate_services(dry_run=True)

    # Check that only us-east-1 work happened and one skip was logged
    # Deleted list contains tuples (region, count)
    # Since our resources default to empty, only the skip count matters via log; no exceptions expected
    assert any("Skipped: service not available in region" in msg for msg in caplog.messages)


def test_orchestrate_all_regions_union(monkeypatch: pytest.MonkeyPatch):
    # When aws.region includes 'all', orchestrator should take union of available regions
    cfg = make_config(["dummy"], ["all"])

    class FakeSession:
        def __init__(self):
            self.behavior = {"resources": {"us-east-1": [1, 2], "eu-central-1": [3]}}
            self.deleted: list[tuple[str, int]] = []

        def get_available_regions(self, service_name: str):
            return ["us-east-1", "eu-central-1"]

    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    holder: dict[str, Any] = {}

    def _mk_session(_cfg):
        s = FakeSession()
        holder["session"] = s
        return s

    monkeypatch.setattr(orch, "create_aws_session", _mk_session)

    with patched_services(monkeypatch, "dummy", DummyHandler):
        orch.orchestrate_services(dry_run=False)

    # Expect deletes recorded for both regions with counts 2 and 1
    session = holder["session"]
    assert sorted(session.deleted) == [("eu-central-1", 1), ("us-east-1", 2)]


def test_orchestrate_failure_path(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    cfg = make_config(["dummy"], ["us-east-1", "eu-west-1"], max_workers=2)

    class FakeSession:
        def __init__(self):
            self.behavior = {"resources": {}, "raise_on_scan": True, "raise_region": "eu-west-1"}
            self.deleted: list[tuple[str, int]] = []

        def get_available_regions(self, service_name: str):
            return ["us-east-1", "eu-west-1"]

    monkeypatch.setattr(orch, "get_config", lambda: cfg)
    monkeypatch.setattr(orch, "create_aws_session", lambda _cfg: FakeSession())

    with patched_services(monkeypatch, "dummy", DummyHandler), caplog.at_level(logging.INFO, logger=orch.__name__):
        orch.orchestrate_services(dry_run=True)

    # Ensure a failure was logged for eu-west-1
    assert any("Task failed" in msg for msg in caplog.messages)
