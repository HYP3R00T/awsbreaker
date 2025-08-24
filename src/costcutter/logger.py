import logging
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any


def _safe_get(obj: Any, attr: str, default: Any) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def setup_logging(config: Any | None = None) -> None:
    """Configure logging.

    - By default, do not emit logs to stdout/stderr (no console handler).
    - Optionally write logs to a per-execution file if enabled via config.

        Config keys supported:
            - logging_level (root level string, e.g. "INFO", "DEBUG").
            - logging.dir (str): directory where log files will be placed. Default: "./logs".
    """

    # Resolve level with fallback
    level = logging.INFO
    lvl_str: Any = None
    logging_section = None
    # Console logging is now disabled (no verbose flag). Only file logging if enabled.
    if config is not None:
        logging_section = _safe_get(config, "logging", None)
        # New preferred key under logging.level
        if logging_section is not None:
            lvl_str = _safe_get(logging_section, "level", None)
        # Backward-compat: top-level logging_level
        if not lvl_str:
            lvl_str = _safe_get(config, "logging_level", None)
    if lvl_str:
        level = getattr(logging, str(lvl_str).upper(), level)

    # Prepare handlers (console when verbose; file when enabled)
    handlers: list[logging.Handler] = []

    log_dir = Path("./logs")
    if logging_section is None and config is not None:
        logging_section = _safe_get(config, "logging", None)
    if logging_section is not None:
        dir_value = _safe_get(logging_section, "dir", str(log_dir))
        try:
            log_dir = Path(str(dir_value)).expanduser()
        except Exception:
            log_dir = Path("./logs")
    # Honor logging.enabled (default True) to toggle file logging.
    enabled = True
    if logging_section is not None:
        try:
            enabled = bool(_safe_get(logging_section, "enabled", True))
        except Exception:
            enabled = True
    if enabled:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = log_dir / f"awsbreaker_{ts}.log"
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            handlers.append(fh)
        except Exception:
            # If we cannot create a file handler, proceed without handlers to avoid crashing.
            handlers = []

    # (No console handler by default; could be added in future via config key.)

    # Apply to root logger
    root = logging.getLogger()
    # Clear any existing handlers to avoid duplicate logs
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)
    for h in handlers:
        root.addHandler(h)

    # Quiet common third-party libraries to reduce noisy INFO logs (e.g., botocore credential messages)
    # Keep our application logs at the configured level while suppressing SDK chatter.
    for name in (
        "boto3",
        "botocore",
        "botocore.credentials",
        "s3transfer",
        "urllib3",
    ):
        with suppress(Exception):
            logging.getLogger(name).setLevel(logging.WARNING)
