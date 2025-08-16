import sys

import typer

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services

app = typer.Typer(help="AWSBreaker — kill-switch for AWS resources when spending limits are breached.")


def run_cli(dry_run: bool | None, verbose: bool | None, no_progress: bool) -> None:
    """Execute the CLI flow with presentation, progress, and summary."""
    # Merge CLI overrides into config so logging respects verbosity
    overrides = {"dry_run": dry_run, "verbose": verbose}
    config = get_config(cli_args=overrides)
    setup_logging(config)

    # Resolve effective flags
    dry_run_eff = dry_run if dry_run is not None else getattr(config, "dry_run", True)
    verbose_eff = verbose if verbose is not None else bool(getattr(config, "verbose", False))

    # Lazy import rich; fall back to plain print if unavailable
    try:
        from rich.console import Console

        console = Console()
    except Exception:
        console = None

    # Header / credits (CLI only)
    try:
        import pyfiglet

        if not verbose_eff:
            banner = pyfiglet.figlet_format("AWSBreaker", font="slant")
            if console:
                console.print(banner.rstrip())
                console.print("\nby HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
                console.print()
            else:
                print(banner.rstrip())
                print("\nby HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
                print()
        else:
            if console:
                console.print("Starting AWSBreaker")
            else:
                print("Starting AWSBreaker")
    except Exception:
        if console:
            console.print("AWSBreaker")
            console.print("by HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
            console.print()
        else:
            print("AWSBreaker")
            print("by HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
            print()

    if console:
        console.print(f"Mode: {'DRY-RUN' if dry_run_eff else 'EXECUTE'}\n")
    else:
        print(f"Mode: {'DRY-RUN' if dry_run_eff else 'EXECUTE'}\n")

    # Progress callback for non-verbose mode
    last_len = 0

    def progress_cb(stats: dict[str, int]) -> None:
        if no_progress or verbose_eff:
            return
        nonlocal last_len
        submitted = stats.get("submitted", 0)
        completed = stats.get("completed", 0)
        pending = stats.get("pending", 0)
        failures = stats.get("failures", 0)
        succeeded = stats.get("succeeded", 0)
        deletions = stats.get("deletions", 0)
        line = (
            f"Progress: completed={completed}/{submitted} pending={pending} "
            f"succeeded={succeeded} failures={failures} deletions={deletions}"
        )
        padded = line.ljust(last_len)
        sys.stdout.write("\r" + padded)
        sys.stdout.flush()
        last_len = len(line)

    summary = orchestrate_services(dry_run=dry_run_eff, progress_cb=progress_cb, print_summary=False)

    if not no_progress and not verbose_eff and last_len > 0:
        sys.stdout.write("\n")
        sys.stdout.flush()

    # Final summary
    submitted = summary.get("submitted", 0)
    skipped = summary.get("skipped", 0)
    failures = summary.get("failures", 0)
    succeeded = summary.get("succeeded", 0)
    deletions = summary.get("deletions", 0)

    if console:
        console.print("\n[bold]Run Summary[/bold]")
        console.print("-----------")
        console.print(f"Tasks submitted   : {submitted}")
        console.print(f"Tasks skipped     : {skipped}")
        console.print(f"Tasks failed      : {failures}")
        console.print(f"Tasks succeeded   : {succeeded}")
        console.print(f"Total deletions   : {deletions}")
    else:
        print("\nRun Summary")
        print("-----------")
        print(f"Tasks submitted   : {submitted}")
        print(f"Tasks skipped     : {skipped}")
        print(f"Tasks failed      : {failures}")
        print(f"Tasks succeeded   : {succeeded}")
        print(f"Total deletions   : {deletions}")


@app.callback(invoke_without_command=True)
def main(
    dry_run: bool | None = typer.Option(
        None,
        "--dry-run/--execute",
        help="Run in dry-run mode (default from config). Use --execute to actually delete resources.",
    ),
    verbose: bool | None = typer.Option(
        None,
        "--verbose/--quiet",
        help="Enable verbose logging (default from config).",
    ),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        is_flag=True,
        help="Disable the compact live progress line.",
    ),
):
    """
    Runs AWSBreaker. If subcommands are added later, this acts as the default.
    """
    run_cli(dry_run=dry_run, verbose=verbose, no_progress=no_progress)


if __name__ == "__main__":
    app()
