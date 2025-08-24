from costcutter.cli import _render_summary_table, _render_table, main, run_cli


class DummyEvent:
    def __init__(self, timestamp="t", region="r", service="s", resource="res", action="a", arn="arn", meta=None):
        self.timestamp = timestamp
        self.region = region
        self.service = service
        self.resource = resource
        self.action = action
        self.arn = arn
        self.meta = meta or {}


class DummyReporter:
    def snapshot(self):
        return [DummyEvent(), DummyEvent(meta={"foo": "bar"})]

    def write_csv(self, path):
        return path


def test_render_table_empty():
    reporter = DummyReporter()
    table = _render_table(reporter, dry_run=True)
    assert table.title.startswith("CostCutter")


def test_render_summary_table_empty():
    reporter = DummyReporter()
    table = _render_summary_table(reporter, dry_run=True)
    assert table.title.startswith("CostCutter")


def test_run_cli(monkeypatch):
    monkeypatch.setattr("costcutter.cli.get_reporter", lambda: DummyReporter())
    monkeypatch.setattr("costcutter.cli.orchestrate_services", lambda dry_run: None)
    run_cli(dry_run=True)


def test_main(monkeypatch):
    class Ctx:
        invoked_subcommand = None

    monkeypatch.setattr("costcutter.cli.run_cli", lambda dry_run, config_file: None)
    main(Ctx(), dry_run=True, config=None)
