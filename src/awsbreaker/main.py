import logging

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging
from awsbreaker.orchestrator import orchestrate_services

logger = logging.getLogger(__name__)


def main() -> None:
    # Load configuration and initialize logging first
    config = get_config()
    setup_logging(config)

    dry_run = getattr(config, "dry_run", True)
    # Print a high-level start message to console (not via logging)
    print(f"Starting AWSBreaker {'in dry-run mode' if dry_run else ''}")

    orchestrate_services(dry_run=dry_run)


if __name__ == "__main__":
    main()
