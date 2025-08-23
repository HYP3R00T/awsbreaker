import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from awsbreaker.reporter import get_reporter

SERVICE: str = "ec2"
RESOURCE: str = "instance"
logger = logging.getLogger(__name__)

_ACCOUNT_ID: str | None = None


def _get_account_id(session: Session) -> str:
    """Return (and cache) the current AWS account id.

    We intentionally keep a simple module-level cache instead of introducing a
    shared helper file per user instruction not to create extra files.
    """
    global _ACCOUNT_ID
    if _ACCOUNT_ID is None:
        try:
            _ACCOUNT_ID = session.client("sts").get_caller_identity().get("Account", "")
        except Exception as e:  # pragma: no cover - extremely unlikely
            logger.error("Failed to resolve account id: %s", e)
            _ACCOUNT_ID = ""
    return _ACCOUNT_ID


def catalog_instances(session: Session, region: str) -> list[str]:
    client = session.client(service_name="ec2", region_name=region)

    arns: list[str] = []
    try:
        reservations = client.describe_instances().get("Reservations", [])
        arns = [i.get("InstanceId") for r in reservations for i in r.get("Instances", [])]
    except ClientError as e:
        logger.error("[%s][ec2] Failed to describe instances: %s", region, e)
        arns = []
    return arns


def cleanup_instance(session: Session, region: str, instance_id: Any, dry_run: bool = True) -> None:
    reporter = get_reporter()
    action = "catalog" if dry_run else "delete"
    status = "discovered" if dry_run else "executing"
    account = _get_account_id(session)
    # Construct proper ARN for the instance resource
    arn = f"arn:aws:ec2:{region}:{account}:instance/{instance_id}"
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
        response = client.terminate_instances(
            InstanceIds=[instance_id],
            Force=True,
            SkipOsShutdown=True,
            DryRun=dry_run,
        )
        ti = response.get("TerminatingInstances", [])
        for inst in ti:
            cur = inst.get("CurrentState", {}).get("Name")
            prev = inst.get("PreviousState", {}).get("Name")
            logger.info(
                "[%s][ec2][instance] terminate requested instance_id=%s previous=%s current=%s dry_run=%s",
                region,
                inst.get("InstanceId"),
                prev,
                cur,
                dry_run,
            )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code") if hasattr(e, "response") else None
        if dry_run and code == "DryRunOperation":
            logger.info("[%s][ec2][instance] dry-run terminate would succeed instance_id=%s", region, instance_id)
        else:
            logger.error("[%s][ec2][instance] terminate failed instance_id=%s error=%s", region, instance_id, e)


def cleanup_instances(session: Session, region: str, dry_run: bool = True, max_workers: int = 1) -> None:
    arns: list = catalog_instances(session=session, region=region)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(cleanup_instance, session, region, arn, dry_run) for arn in arns]
        for fut in as_completed(futures):
            fut.result()
