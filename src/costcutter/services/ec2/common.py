import logging

from boto3.session import Session

_ACCOUNT_ID: str | None = None

logger = logging.getLogger(__name__)


def _get_account_id(session: Session) -> str:
    """Return (and cache) the current AWS account id (simple module cache)."""
    global _ACCOUNT_ID
    if _ACCOUNT_ID is None:
        try:
            _ACCOUNT_ID = session.client("sts").get_caller_identity().get("Account", "")
        except Exception as e:  # pragma: no cover
            logger.error("Failed to resolve account id: %s", e)
            _ACCOUNT_ID = ""
    return _ACCOUNT_ID
