# src/awsbreaker/cli.py
from __future__ import annotations

import threading
import time
from pathlib import Path

import typer
from pyfiglet import Figlet
from rich.console import Console
from rich.live import Live
from rich.table import Table

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services
from awsbreaker.reporter import get_reporter

TAIL_COUNT = 10  # number of most recent events to display


def _render_table(reporter, dry_run: bool) -> Table:
    """Render a Rich table of recorded events.

    Adds a placeholder row while no events have been recorded yet so the
    interface never appears visually "empty" and communicates dry-run mode.
    """
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    all_events = reporter.snapshot()
    events = all_events[-TAIL_COUNT:]
    table = Table(title=f"AWSBreaker — Live events ({mode}, last {TAIL_COUNT})")
    table.add_column("Time", no_wrap=True, style="dim")
    table.add_column("Region", style="cyan")
    table.add_column("Service", style="magenta")
    table.add_column("Resource", style="green")
    table.add_column("Action", style="yellow")
    table.add_column("ID", overflow="fold")
    table.add_column("Meta", overflow="fold")
    if not all_events:
        # Placeholder row communicates status instead of an empty table body
        table.add_row(
            "-",
            "-",
            "-",
            "-",
            "waiting",
            "-",
            "No resource events yet (dry run)" if dry_run else "No resource events yet",
        )
        return table
    if len(all_events) > TAIL_COUNT:
        table.caption = f"Showing last {TAIL_COUNT} of {len(all_events)} events"

    for e in events:
        meta = ""
        try:
            # keep meta compact
            meta = ", ".join(f"{k}={v}" for k, v in (e.meta or {}).items())
        except Exception:
            meta = str(e.meta)
        table.add_row(
            getattr(e, "timestamp", ""),
            getattr(e, "region", ""),
            getattr(e, "service", ""),
            getattr(e, "resource", ""),
            getattr(e, "action", ""),
            getattr(e, "arn", "") or "",
            meta,
        )
    return table


def _render_summary_table(reporter, dry_run: bool) -> Table:
    """Render an aggregated summary of all recorded events.

    Groups by (service, resource, action) and counts occurrences.
    """
    events = reporter.snapshot()
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    table = Table(title=f"AWSBreaker — Summary ({mode})")
    table.add_column("Service", style="magenta")
    table.add_column("Resource", style="green")
    table.add_column("Action", style="yellow")
    table.add_column("Count", justify="right")
    if not events:
        table.add_row("-", "-", "-", "0")
        return table
    counts: dict[tuple[str, str, str], int] = {}
    for e in events:
        key = (
            getattr(e, "service", ""),
            getattr(e, "resource", ""),
            getattr(e, "action", ""),
        )
        counts[key] = counts.get(key, 0) + 1
    for svc, res, act in sorted(counts.keys()):
        table.add_row(svc, res, act, str(counts[(svc, res, act)]))
    table.caption = f"Total events: {len(events)}"
    return table


def run_cli(dry_run: bool | None = None, config_file: Path | None = None) -> None:
    """Run the awsbreaker CLI with a live updating event tail and final summary.

    The CLI now always shows the Rich live progress UI; simplified per design change.
    """
    overrides = {"dry_run": dry_run}
    config = get_config(cli_args=overrides, config_file=config_file)
    setup_logging(config)

    dry_run_eff = dry_run if dry_run is not None else getattr(config, "dry_run", True)

    console = Console()

    banner_text = "AWSBreaker"
    credit_line = "Author: HYP3R00T  GitHub: https://github.com/HYP3R00T  Site: https://hyperoot.dev"

    # Clear screen and show banner + credits once
    try:
        console.clear()
    except Exception:
        print("\033c", end="")

    fig_rendered: str | None = None
    try:
        fig = Figlet(font="slant")
        fig_rendered = fig.renderText(banner_text)
    except Exception:
        fig_rendered = None

    if fig_rendered:
        console.print(f"[bold cyan]{fig_rendered}[/bold cyan]")
    else:
        console.print(f"[bold]{banner_text}[/bold]")
    console.print(f"{credit_line}\n")

    reporter = get_reporter()

    # Orchestrator runs in separate thread so Live table can update on main thread
    orchestrator_exc: list[Exception] = []

    def _run_orchestrator():
        try:
            orchestrate_services(dry_run=dry_run_eff)
        except Exception as exc:
            orchestrator_exc.append(exc)

    orb_thread = threading.Thread(target=_run_orchestrator, daemon=True)
    orb_thread.start()

    try:
        # Rich live table path (always enabled now)
        with Live(_render_table(reporter, dry_run_eff), refresh_per_second=4, console=console) as live:
            while orb_thread.is_alive():
                live.update(_render_table(reporter, dry_run_eff))
                time.sleep(0.25)
            # final update
            live.update(_render_table(reporter, dry_run_eff))
    except KeyboardInterrupt:
        console.print("\nInterrupted by user. Waiting for tasks to stop...")
    finally:
        orb_thread.join(timeout=5)
        if orchestrator_exc:
            # re-raise first exception
            raise orchestrator_exc[0]
        # final summary: clear screen, show banner again, then summary only
        try:
            console.clear()
        except Exception:
            print("\033c", end="")
        if fig_rendered:
            console.print(f"[bold cyan]{fig_rendered}[/bold cyan]")
        else:
            console.print(f"[bold]{banner_text}[/bold]")
        console.print(credit_line + "\n")
        console.print(_render_summary_table(reporter, dry_run_eff))
        try:
            reporting_cfg = getattr(config, "reporting", None)
            csv_cfg = getattr(reporting_cfg, "csv", None) if reporting_cfg else None
            if csv_cfg and getattr(csv_cfg, "enabled", False):
                path = getattr(csv_cfg, "path", "./events.csv")
                saved = reporter.write_csv(path)
                console.print(f"[green]Events exported to CSV:[/green] {saved}")
        except Exception as exc:
            console.print(f"[red]Failed to write CSV report: {exc}[/red]")


app = typer.Typer(help="AWSBreaker – Kill-switch style cleanup tool for AWS resources.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool | None = None,
    config: Path | None = None,
):
    """Run AWSBreaker (no subcommands yet)."""
    if config is not None and config.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
        raise typer.BadParameter("Config file must be one of: .yaml, .yml, .toml, .json")
    run_cli(dry_run=dry_run, config_file=config)
    if ctx.invoked_subcommand is None:
        return


if __name__ == "__main__":
    app()
