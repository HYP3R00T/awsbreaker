import logging
import sys
from typing import Any

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services

logger = logging.getLogger(__name__)


def _print_header(verbose: bool) -> None:
    """Pretty header for non-verbose mode; simple print when verbose."""
    try:
        import pyfiglet  # type: ignore

        if not verbose:
            banner = pyfiglet.figlet_format("AWSBreaker", font="slant")
            print(banner.rstrip())
            print("\nby HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
            print()
        else:
            print("Starting AWSBreaker")
    except Exception:
        # Fallback to minimal header if pyfiglet missing or fails
        print("AWSBreaker")
        print("by HYP3R00T  |  https://hyperoot.dev  |  https://github.com/HYP3R00T")
        print()


def _print_summary(summary: dict[str, Any], verbose: bool) -> None:
    """Organized multi-line summary for the whole run."""
    submitted = summary.get("submitted", 0)
    skipped = summary.get("skipped", 0)
    failures = summary.get("failures", 0)
    succeeded = summary.get("succeeded", 0)
    deletions = summary.get("deletions", 0)

    print("\nRun Summary")
    print("-----------")
    print(f"Tasks submitted   : {submitted}")
    print(f"Tasks skipped     : {skipped}")
    print(f"Tasks failed      : {failures}")
    print(f"Tasks succeeded   : {succeeded}")
    print(f"Total deletions   : {deletions}")
    if verbose:
        print("(Verbose logging enabled — see log for detailed events)")


def main() -> None:
    # Load configuration and initialize logging first
    config = get_config()
    setup_logging(config)

    dry_run = getattr(config, "dry_run", True)
    verbose = bool(getattr(config, "verbose", False))

    # Pretty header / credits
    _print_header(verbose)
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}\n")

    # Live progress for non-verbose mode: print compact counts as tasks finish
    progress_last: dict[str, Any] | None = None
    progress_last_len: int = 0

    def progress_cb(stats: dict[str, int]) -> None:
        nonlocal progress_last
        progress_last = stats
        if not verbose:
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
            # Overwrite the same line in-place; pad with spaces to clear remnants
            nonlocal progress_last_len
            padded = line.ljust(progress_last_len)
            sys.stdout.write("\r" + padded)
            sys.stdout.flush()
            progress_last_len = len(line)

    summary = orchestrate_services(dry_run=dry_run, progress_cb=progress_cb, print_summary=False)
    if not verbose and progress_last_len > 0:
        # Move to the next line before final summary output
        sys.stdout.write("\n")
        sys.stdout.flush()
    _print_summary(summary, verbose)


if __name__ == "__main__":
    main()
