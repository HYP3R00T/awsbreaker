import sys
from types import SimpleNamespace


class DummyConsole:
    def __init__(self):
        self.lines: list[str] = []

    def print(self, *args, **kwargs):  # noqa: D401, ARG002
        self.lines.append(" ".join(str(a) for a in args))


def test_cli_run_flow_progress_and_summary(monkeypatch, capsys):
    # Patch config and logging
    cfg = SimpleNamespace(dry_run=True, verbose=False)

    def fake_get_config(cli_args=None):  # noqa: D401, ARG001
        # emulate config object with attributes used in cli.run_cli
        return SimpleNamespace(dry_run=cfg.dry_run, verbose=cfg.verbose, aws=SimpleNamespace())

    def fake_setup_logging(_cfg):  # noqa: D401, ARG001
        return None

    # patch orchestrate_services to simulate work and exercise progress callback
    def fake_orchestrate_services(*, dry_run, progress_cb, print_summary):  # noqa: D401
        assert dry_run is True
        assert print_summary is False
        # simulate two updates and final summary
        if progress_cb:
            progress_cb({
                "submitted": 2,
                "skipped": 0,
                "failures": 0,
                "succeeded": 0,
                "deletions": 0,
                "completed": 0,
                "pending": 2,
            })
            progress_cb({
                "submitted": 2,
                "skipped": 0,
                "failures": 0,
                "succeeded": 1,
                "deletions": 1,
                "completed": 2,
                "pending": 0,
            })
        return {"submitted": 2, "skipped": 0, "failures": 0, "succeeded": 1, "deletions": 1}

    import awsbreaker.cli as cli

    # Avoid importing rich/pyfiglet to keep output deterministic
    monkeypatch.setitem(sys.modules, "rich.console", None)
    monkeypatch.setitem(sys.modules, "pyfiglet", None)

    monkeypatch.setattr(cli, "get_config", fake_get_config)
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "orchestrate_services", fake_orchestrate_services)

    # run with no_progress False to exercise progress line; verbose=False ensures banner path
    cli.run_cli(dry_run=True, verbose=False, no_progress=False)

    out = capsys.readouterr().out
    assert "Mode: DRY-RUN" in out
    assert "Run Summary" in out
    assert "Tasks submitted" in out


def test_cli_with_console_and_verbose_banner(monkeypatch, capsys):
    import awsbreaker.cli as cli

    # Provide a dummy Console implementation via the rich.console module
    class ConsoleModule:
        class Console:  # noqa: D401
            def __init__(self):
                self.lines = []

            def print(self, *args, **kwargs):  # noqa: D401, ARG002
                # mimic console printing by writing to stdout
                print(" ".join(str(a) for a in args))

    # Provide a dummy pyfiglet with figlet_format
    class PyFigletModule:
        @staticmethod
        def figlet_format(text, font=None):  # noqa: D401, ARG002
            return f"BANNER:{text}"

    monkeypatch.setitem(sys.modules, "rich.console", ConsoleModule)
    monkeypatch.setitem(sys.modules, "pyfiglet", PyFigletModule)

    # Config verbose False triggers banner path
    def fake_get_config(cli_args=None):  # noqa: D401, ARG001
        return SimpleNamespace(dry_run=True, verbose=False, aws=SimpleNamespace())

    def fake_setup_logging(_cfg):
        return None

    def fake_orchestrate_services(*, dry_run, progress_cb, print_summary):  # noqa: D401, ARG002
        assert dry_run is True
        # call progress once to ensure callback doesn't explode with console present
        if progress_cb:
            progress_cb({
                "submitted": 1,
                "skipped": 0,
                "failures": 0,
                "succeeded": 0,
                "deletions": 0,
                "completed": 0,
                "pending": 1,
            })
        return {"submitted": 1, "skipped": 0, "failures": 0, "succeeded": 0, "deletions": 0}

    monkeypatch.setattr(cli, "get_config", fake_get_config)
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "orchestrate_services", fake_orchestrate_services)

    cli.run_cli(dry_run=True, verbose=None, no_progress=True)
    out = capsys.readouterr().out
    assert "BANNER:AWSBreaker" in out
    assert "Mode: DRY-RUN" in out
    assert "Run Summary" in out


def test_cli_verbose_quiet_flags_override(monkeypatch, capsys):
    import awsbreaker.cli as cli

    # Config defaults verbose=True, but cli overrides to quiet
    cfg = SimpleNamespace(dry_run=False, verbose=True)

    def fake_get_config(cli_args=None):  # noqa: D401, ARG001
        return SimpleNamespace(dry_run=cfg.dry_run, verbose=cfg.verbose, aws=SimpleNamespace())

    def fake_setup_logging(_cfg):
        return None

    def fake_orchestrate_services(*, dry_run, progress_cb, print_summary):  # noqa: D401, ARG002
        assert dry_run is False
        assert progress_cb is not None  # still created, but will be a no-op due to verbose
        return {"submitted": 0, "skipped": 0, "failures": 0, "succeeded": 0, "deletions": 0}

    monkeypatch.setitem(sys.modules, "rich.console", None)
    monkeypatch.setitem(sys.modules, "pyfiglet", None)

    monkeypatch.setattr(cli, "get_config", fake_get_config)
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "orchestrate_services", fake_orchestrate_services)

    # verbose flag is None so it should read from cfg (True) and take the verbose path
    cli.run_cli(dry_run=False, verbose=None, no_progress=True)

    out = capsys.readouterr().out
    # In verbose mode there should still be a summary header printed at the end
    assert "Run Summary" in out


def test_typer_callback_invokes_run_cli(monkeypatch):
    import awsbreaker.cli as cli

    called = {"ok": False}

    def fake_run_cli(dry_run, verbose, no_progress):  # noqa: D401, ARG001
        called["ok"] = True

    monkeypatch.setattr(cli, "run_cli", fake_run_cli)

    # Call the Typer callback directly with options
    cli.main(dry_run=None, verbose=None, no_progress=False)
    assert called["ok"] is True
