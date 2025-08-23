import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from awsbreaker.reporter import get_reporter

SERVICE: str = "ec2"
RESOURCE: str = "instances"
logger = logging.getLogger(__name__)


def catalog_instances(session: Session, region: str) -> list:
    reporter = get_reporter()
    client = session.client(service_name="ec2", region_name=region)

    arns: list[dict[str, Any]] = []
    try:
        reservations = client.describe_instances().get("Reservations", [])
        arns = [i.get("InstanceId") for r in reservations for i in r.get("Instances", [])]
        for arn in arns:
            reporter.record(service=SERVICE, resource=RESOURCE, action="Delete", arn=arn)
    except ClientError as e:
        logger.error("[%s][ec2] Failed to describe instances: %s", region, e)
        arns = []
    return arns


def cleanup_instance(session: Session, region: str, arn: Any, dry_run: bool = True) -> None:
    reporter = get_reporter()
    reporter.record(service=SERVICE, resource=RESOURCE, action="Delete", arn=arn)
    client = session.client("ec2", region_name=region)
    response = client.terminate_instances(InstanceIds=[arn], Force=True, SkipOsShutdown=True, DryRun=dry_run)  # noqa: F841
    # Response Syntax
    # {
    #     'TerminatingInstances': [
    #         {
    #             'InstanceId': 'string',
    #             'CurrentState': {
    #                 'Code': 123,
    #                 'Name': 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
    #             },
    #             'PreviousState': {
    #                 'Code': 123,
    #                 'Name': 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
    #             }
    #         },
    #     ]
    # }


def cleanup_instances(session: Session, region: str, dry_run: bool = True, max_workers: int = 1) -> None:
    arns: list = catalog_instances(session=session, region=region)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs: dict[Any, tuple[str, str]] = {}
        for arn in arns:
            fut = ex.submit(cleanup_instance, session, region, arn, dry_run)
            futs.append(fut)
        for f in as_completed(futs):
            f.result()
