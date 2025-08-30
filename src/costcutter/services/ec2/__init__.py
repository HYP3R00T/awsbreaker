import logging

from boto3.session import Session

from costcutter.services.ec2.instances import cleanup_instances
from costcutter.services.ec2.key_pairs import cleanup_key_pairs

logger = logging.getLogger(__name__)
_ACCOUNT_ID: str | None = None
_HANDLERS = {"instances": cleanup_instances, "key_pairs": cleanup_key_pairs}


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


def cleanup_ec2(session: Session, region: str, dry_run: bool = True, max_workers: int = 1):
    # targets: list[str] or None => run all registered
    for fn in _HANDLERS.values():
        fn(session=session, region=region, dry_run=dry_run, max_workers=max_workers)
