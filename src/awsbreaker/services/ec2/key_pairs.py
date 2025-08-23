import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from awsbreaker.reporter import get_reporter

SERVICE: str = "ec2"
RESOURCE: str = "instances"
logger = logging.getLogger(__name__)


def catalog_key_pairs(session: Session, region: str) -> list:
    reporter = get_reporter()
    client = session.client(service_name="ec2", region_name=region)

    arns: list[dict[str, Any]] = []
    try:
        keypairs = client.describe_key_pairs().get("KeyPairs", [])
        arns.extend([k.get("KeyPairId") for k in keypairs])
        for arn in arns:
            reporter.record(service=SERVICE, resource=RESOURCE, action="Delete", arn=arn)
    except ClientError as e:
        logger.error("[%s][ec2] Failed to describe key pairs: %s", region, e)
        arns = []
    return arns


def cleanup_key_pair(session: Session, region: str, key_pair_id: str, dry_run: bool = True) -> None:
    reporter = get_reporter()
    reporter.record(service=SERVICE, resource=RESOURCE, action="Delete", arn=key_pair_id)
    client = session.client("ec2", region_name=region)
    response = client.delete_key_pair(KeyPairId=key_pair_id, DryRun=dry_run)  # noqa: F841
    # Response Syntax
    # {
    #     'Return': True|False,
    #     'KeyPairId': 'string'
    # }


def cleanup_key_pairs(session: Session, region: str, dry_run: bool = True, max_workers: int = 1) -> None:
    arns: list = catalog_key_pairs(session=session, region=region)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs: dict[Any, tuple[str, str]] = {}
        for arn in arns:
            fut = ex.submit(cleanup_key_pair, session, region, arn, dry_run)
            futs.append(fut)
        for f in as_completed(futs):
            f.result()
