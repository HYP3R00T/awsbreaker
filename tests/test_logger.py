import logging
from contextlib import contextmanager

import pytest

from awsbreaker.logger import setup_logging


@contextmanager
def isolated_root_logger():
    """Temporarily isolate the root logger so basicConfig can take effect.

    - Removes existing handlers so logging.basicConfig() configures fresh.
    - Restores previous handlers and level after the test.
    """
    root = logging.getLogger()
    old_level = root.level
    old_handlers = list(root.handlers)
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        yield root
    finally:
        # Remove handlers added during the test
        for h in list(root.handlers):
            root.removeHandler(h)
        # Restore original state
        root.setLevel(old_level)
        for h in old_handlers:
            root.addHandler(h)


def test_setup_logging_defaults_to_info(capsys: pytest.CaptureFixture[str]):
    with isolated_root_logger():
        setup_logging(None)
        logger = logging.getLogger(__name__)
        logger.info("hello info")
        logger.debug("hello debug")

        out = capsys.readouterr().out
        assert " - INFO - hello info" in out
        assert " - DEBUG - hello debug" not in out


def test_setup_logging_respects_debug_level(capsys: pytest.CaptureFixture[str]):
    class Cfg:
        logging_level = "debug"

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.debug("hello debug")

        out = capsys.readouterr().out
        assert " - DEBUG - hello debug" in out


def test_setup_logging_invalid_level_falls_back_to_info(capsys: pytest.CaptureFixture[str]):
    class Cfg:
        logging_level = "not-a-level"

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.info("hello info")
        logger.debug("hello debug")

        out = capsys.readouterr().out
        assert " - INFO - hello info" in out
        assert " - DEBUG - hello debug" not in out
