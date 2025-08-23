import pyfiglet
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

    if not verbose_eff:
        banner = pyfiglet.figlet_format("AWSBreaker", font="slant")

        console.print(banner.rstrip())
        console.print("\nby HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
        console.print()
    else:
        console.print("Starting AWSBreaker")
    print(f"Mode: {'DRY-RUN' if dry_run_eff else 'EXECUTE'}\n")

    orchestrate_services(dry_run=dry_run_eff)


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
