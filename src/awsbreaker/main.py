import json
import logging

from awsbreaker.conf.config import get_config
from awsbreaker.logger import setup_logging

config = get_config()
setup_logging(config)

logger = logging.getLogger(__name__)
logger.info("Logging is configured")


def main():
    config = get_config()
    logger.info(json.dumps(config.to_dict(), indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
