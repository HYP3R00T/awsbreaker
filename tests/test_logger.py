import logging
from contextlib import contextmanager
from pathlib import Path

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


def test_setup_logging_defaults_to_info_no_console(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    class Cfg:
        logging_level = "INFO"
        logging = type("L", (), {"file_enabled": False, "dir": str(tmp_path)})()

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.info("hello info")
        logger.debug("hello debug")

        # No console output expected
        out = capsys.readouterr().out
        assert out == ""


def test_setup_logging_respects_debug_level_file_enabled(tmp_path: Path):
    class Cfg:
        logging_level = "debug"
        logging = type("L", (), {"file_enabled": True, "dir": str(tmp_path)})()

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.debug("hello debug")

        # Expect a log file created with the debug message inside
        files = list(tmp_path.glob("*.log"))
        assert files, "expected a log file to be created"
        content = files[0].read_text()
        assert "DEBUG - hello debug" in content


def test_setup_logging_invalid_level_falls_back_to_info_file(tmp_path: Path):
    class Cfg:
        logging_level = "not-a-level"
        logging = type("L", (), {"file_enabled": True, "dir": str(tmp_path)})()

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.info("hello info")
        logger.debug("hello debug")

        files = list(tmp_path.glob("*.log"))
        assert files, "expected a log file to be created"
        content = files[0].read_text()
        assert "INFO - hello info" in content
        assert "DEBUG - hello debug" not in content


def test_setup_logging_disabled(tmp_path: Path, capsys):
    class Cfg:
        logging_level = "INFO"
        logging = type("L", (), {"enabled": False, "dir": str(tmp_path)})()

    with isolated_root_logger():
        setup_logging(Cfg())
        logger = logging.getLogger(__name__)
        logger.info("hello info")

        # No files should be created
        files = list(tmp_path.glob("*.log"))
        assert not files
        # Also no console output
        out = capsys.readouterr().out
        assert out == ""
