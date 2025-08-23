import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from boto3.session import Session
from botocore.exceptions import ClientError

from awsbreaker.reporter import get_reporter

SERVICE: str = "ec2"
RESOURCE: str = "key_pair"
logger = logging.getLogger(__name__)

_ACCOUNT_ID: str | None = None


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


def catalog_key_pairs(session: Session, region: str) -> list[str]:
    client = session.client(service_name="ec2", region_name=region)

    arns: list[str] = []
    try:
        keypairs = client.describe_key_pairs().get("KeyPairs", [])
        arns.extend([k.get("KeyPairId") for k in keypairs])
    except ClientError as e:
        logger.error("[%s][ec2] Failed to describe key pairs: %s", region, e)
        arns = []
    return arns


def cleanup_key_pair(session: Session, region: str, key_pair_id: str, dry_run: bool = True) -> None:
    reporter = get_reporter()
    action = "catalog" if dry_run else "delete"
    status = "discovered" if dry_run else "executing"
    account = _get_account_id(session)
    arn = f"arn:aws:ec2:{region}:{account}:key-pair/{key_pair_id}"
    reporter.record(
        region,
        SERVICE,
        RESOURCE,
        action,
        arn=arn,
        meta={"status": status, "dry_run": dry_run},
    )
    client = session.client("ec2", region_name=region)
    try:
        response = client.delete_key_pair(KeyPairId=key_pair_id, DryRun=dry_run)
        logger.info(
            "[%s][ec2][key_pair] delete requested key_pair_id=%s return=%s dry_run=%s",
            region,
            response.get("KeyPairId", key_pair_id),
            response.get("Return"),
            dry_run,
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code") if hasattr(e, "response") else None
        if dry_run and code == "DryRunOperation":
            logger.info("[%s][ec2][key_pair] dry-run delete would succeed key_pair_id=%s", region, key_pair_id)
        else:
            logger.error("[%s][ec2][key_pair] delete failed key_pair_id=%s error=%s", region, key_pair_id, e)


def cleanup_key_pairs(session: Session, region: str, dry_run: bool = True, max_workers: int = 1) -> None:
    arns: list = catalog_key_pairs(session=session, region=region)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(cleanup_key_pair, session, region, arn, dry_run) for arn in arns]
        for fut in as_completed(futures):
            fut.result()
