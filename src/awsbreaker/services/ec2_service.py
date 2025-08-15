import logging
from typing import Any

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _get_name_tag(tags: list[dict[str, Any]] | None) -> str | None:
    if not tags:
        return None
    for t in tags:
        if t.get("Key") == "Name":
            return t.get("Value")
    return None


def run(session: Any, region: str, dry_run: bool, reporter) -> int:
    """EC2 single entrypoint: plan -> (maybe) execute.

    Returns number of successfully issued deletions (instances terminated).
    """
    client = session.client("ec2", region_name=region)

    # PLAN: list instances
    instances: list[dict[str, Any]] = []
    try:
        reservations = client.describe_instances().get("Reservations", [])
        instances = [i for r in reservations for i in r.get("Instances", [])]
    except ClientError as e:
        logger.error("[%s][ec2] Failed to describe instances: %s", region, e)
        instances = []

    for inst in instances:
        iid = inst.get("InstanceId")
        name = _get_name_tag(inst.get("Tags"))
        state = (inst.get("State") or {}).get("Name")
        reporter({
            "phase": "PLAN",
            "service": "ec2",
            "region": region,
            "resource_type": "instance",
            "id": iid,
            "name": name,
            "action": "delete",
            "status": "planned",
            "extra": {"state": state},
        })

    if dry_run:
        return 0

    # EXECUTE: terminate instances
    deleted = 0
    for inst in instances:
        iid = inst.get("InstanceId")
        try:
            client.terminate_instances(InstanceIds=[iid])
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "instance",
                "id": iid,
                "action": "delete",
                "status": "success",
            })
            deleted += 1
        except ClientError as e:
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "instance",
                "id": iid,
                "action": "delete",
                "status": "failed",
                "reason": str(e),
            })

    return deleted
