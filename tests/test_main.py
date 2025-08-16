from types import SimpleNamespace


def test_run_calls_orchestrate_with_effective_dry_run(monkeypatch):
    calls: dict[str, object] = {}

    # Fake config returned by get_config
    cfg = SimpleNamespace(dry_run=False)

    def fake_get_config():
        return cfg

    def fake_setup_logging(_cfg):
        calls["logging"] = True

    def fake_orchestrate_services(*, dry_run, progress_cb, print_summary):  # noqa: D401
        # Capture parameters to validate behavior
        calls["dry_run"] = dry_run
        calls["progress_cb"] = progress_cb
        calls["print_summary"] = print_summary
        return {"submitted": 0, "skipped": 0, "failures": 0, "succeeded": 0, "deletions": 0}

    import awsbreaker.main as m

    monkeypatch.setattr(m, "get_config", fake_get_config)
    monkeypatch.setattr(m, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(m, "orchestrate_services", fake_orchestrate_services)

    # Override dry_run to True and ensure it is passed through
    out = m.run(dry_run=True)
    assert out["submitted"] == 0
    assert calls["dry_run"] is True
    assert calls["progress_cb"] is None
    assert calls["print_summary"] is False


def test_main_invokes_run(monkeypatch):
    import awsbreaker.main as m

    invoked = {"run": False}

    def fake_run(dry_run=None):  # noqa: D401, ARG001
        invoked["run"] = True
        return {}

    monkeypatch.setattr(m, "run", fake_run)

    # Should not raise and should call run()
    m.main()
    assert invoked["run"] is True
