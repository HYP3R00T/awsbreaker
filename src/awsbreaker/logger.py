import logging
import sys


def setup_logging(config=None) -> None:
    level = logging.INFO
    if config is not None:
        lvl_str = getattr(config, "logging_level", None)
        if lvl_str:
            level = getattr(logging, str(lvl_str).upper(), level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
