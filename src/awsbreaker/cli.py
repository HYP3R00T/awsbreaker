# src/awsbreaker/cli.py
from __future__ import annotations

import argparse
import threading
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services
from awsbreaker.reporter import get_reporter


def _render_table(reporter, dry_run: bool) -> Table:  # type: ignore
    """Render a Rich table of recorded events.

    Adds a placeholder row while no events have been recorded yet so the
    interface never appears visually "empty" and communicates dry-run mode.
    """
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    table = Table(title=f"AWSBreaker — Live events ({mode})")
    table.add_column("Time", no_wrap=True, style="dim")
    table.add_column("Region", style="cyan")
    table.add_column("Service", style="magenta")
    table.add_column("Resource", style="green")
    table.add_column("Action", style="yellow")
    table.add_column("ID", overflow="fold")
    table.add_column("Meta", overflow="fold")
    events = reporter.snapshot()
    if not events:
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


def _plain_stream(reporter):
    # Simple fallback printer if Rich isn't installed
    printed = 0
    try:
        while True:
            events = reporter.snapshot()
            if len(events) > printed:
                for e in events[printed:]:
                    meta = ", ".join(f"{k}={v}" for k, v in (e.meta or {}).items())
                    print(f"[{e.timestamp}] {e.region} {e.service}/{e.resource} {e.action} id={e.arn or ''} {meta}")
                printed = len(events)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return


def run_cli(dry_run: bool | None = None, verbose: bool | None = None, no_progress: bool = False) -> None:
    # Merge CLI overrides into config so logging respects verbosity
    overrides = {"dry_run": dry_run, "verbose": verbose}
    config = get_config(cli_args=overrides)
    setup_logging(config)

    dry_run_eff = dry_run if dry_run is not None else getattr(config, "dry_run", True)
    verbose_eff = verbose if verbose is not None else bool(getattr(config, "verbose", False))

    console = Console() if Console else None

    if console:
        banner = "AWSBreaker" if verbose_eff else "AWSBreaker"
        console.print(f"[bold]{banner}[/bold]\nMode: {'DRY-RUN' if dry_run_eff else 'EXECUTE'}\n")
    else:
        print(f"AWSBreaker — Mode: {'DRY-RUN' if dry_run_eff else 'EXECUTE'}\n")

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
        if console and Live and Table and not no_progress:
            # Rich live table path
            with Live(_render_table(reporter, dry_run_eff), refresh_per_second=4, console=console) as live:
                while orb_thread.is_alive():
                    live.update(_render_table(reporter, dry_run_eff))
                    time.sleep(0.25)
                # final update
                live.update(_render_table(reporter, dry_run_eff))
        else:
            # Fallback plain streaming
            _plain_stream(reporter)
    except KeyboardInterrupt:
        # user interrupted; continue to join the thread and exit cleanly
        if console:
            console.print("\nInterrupted by user. Waiting for tasks to stop...")
    finally:
        orb_thread.join(timeout=5)
        if orchestrator_exc:
            # re-raise first exception
            raise orchestrator_exc[0]
        # final summary / flush reporter if desired
        if console:
            console.print("\nRun complete. Events recorded:", reporter.count())
        else:
            print("\nRun complete. Events recorded:", reporter.count())


def app():
    parser = argparse.ArgumentParser(prog="awsbreaker")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Perform a dry run (default from config)")
    parser.add_argument("--execute", action="store_true", default=None, help="Execute deletions (overrides dry-run)")
    parser.add_argument("--verbose", action="store_true", default=None, help="Verbose logging")
    parser.add_argument("--no-progress", action="store_true", default=False, help="Disable live progress UI")
    args = parser.parse_args()

    # normalize dry-run flag: --execute takes precedence
    dry = False if args.execute else True if args.dry_run else None

    run_cli(dry_run=dry, verbose=args.verbose if args.verbose else None, no_progress=args.no_progress)


if __name__ == "__main__":
    app()
