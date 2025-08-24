import logging
from typing import Any

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services

logger = logging.getLogger(__name__)


def run(dry_run: bool | None = None) -> dict[str, Any]:
    """
    Programmatic API to execute AWSBreaker without printing to stdout.

    This function loads config, initializes logging, executes orchestration,
    and returns a summary dict. All user-facing presentation (headers,
    progress, summaries) should be handled by the CLI or the caller.

    Args:
        dry_run: Override dry-run mode. If None, uses value from config.

    Returns:
        A summary dict with counters for the run.
    """
    # Load configuration and initialize logging first
    config = get_config()
    setup_logging(config)

    # Resolve effective flags (config > defaults, with optional override)
    dry_run_eff = dry_run if dry_run is not None else getattr(config, "dry_run", True)

    # Execute without progress reporting or printing; rely on logging instead
    summary = orchestrate_services(dry_run=dry_run_eff)
    return summary


def main() -> None:
    # Minimal __main__ execution: no printing, just run with defaults
    run()


if __name__ == "__main__":
    main()
