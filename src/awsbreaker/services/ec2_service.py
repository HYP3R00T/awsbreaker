import contextlib
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
    """Plan and delete EC2 instances, plus a small, instance-scoped cleanup.

    Scope kept intentionally small and cheap:
    - Instances: plan + terminate
    - EIPs: only those associated with the just-terminated instances
    - EBS volumes: only those attached to those instances with DeleteOnTermination=False
    """
    client = session.client("ec2", region_name=region)

    # PLAN: instances
    # List all instances in the region. We flatten Reservations -> Instances.
    # Describe APIs don't incur charges; we use them to avoid deleting things that auto-delete.
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

    # PLAN: minimal, instance-scoped extras (EIPs and keep-volumes)
    # Only look at resources directly tied to the discovered instances to keep calls cheap.
    iids = [i.get("InstanceId") for i in instances if i.get("InstanceId")]
    eips: list[dict[str, Any]] = []
    volumes_to_consider: list[dict[str, Any]] = []
    if iids:
        try:
            # EIPs currently associated to these instances. These incur charges when left unassociated later.
            eips = client.describe_addresses(Filters=[{"Name": "instance-id", "Values": iids}]).get("Addresses", [])
        except ClientError:
            eips = []
        try:
            # Volumes attached to these instances. We'll only plan delete for those marked DeleteOnTermination=False.
            vols_resp = client.describe_volumes(Filters=[{"Name": "attachment.instance-id", "Values": iids}])
            volumes_to_consider = vols_resp.get("Volumes", [])
        except ClientError:
            volumes_to_consider = []

    for a in eips:
        reporter({
            "phase": "PLAN",
            "service": "ec2",
            "region": region,
            "resource_type": "eip",
            "id": a.get("AllocationId") or a.get("PublicIp"),
            "name": a.get("PublicIp"),
            "action": "release",
            "status": "planned",
        })

    def _volume_marked_keep(v: dict[str, Any]) -> bool:
        # True when any attachment explicitly opts out of auto-delete on termination.
        return any(att.get("DeleteOnTermination") is False for att in (v.get("Attachments", []) or []))

    for v in volumes_to_consider:
        if _volume_marked_keep(v):
            reporter({
                "phase": "PLAN",
                "service": "ec2",
                "region": region,
                "resource_type": "volume",
                "id": v.get("VolumeId"),
                "name": _get_name_tag(v.get("Tags")),
                "action": "delete",
                "status": "planned",
            })

    # PLAN: final sweep candidates to stop residual EC2 charges
    # After instance termination, typical billable leftovers are:
    # - Unassociated EIPs
    # - Available (detached) EBS volumes
    # - Self-owned EBS snapshots
    unassoc_eips: list[dict[str, Any]] = []
    available_volumes: list[dict[str, Any]] = []
    owned_snapshots: list[dict[str, Any]] = []
    try:
        # All EIPs; filter locally to keep API usage simple.
        all_eips = client.describe_addresses().get("Addresses", [])
        unassoc_eips = [a for a in all_eips if not a.get("AssociationId")]
    except ClientError:
        unassoc_eips = []
    try:
        # Volumes that are already detached and billable.
        available_volumes = client.describe_volumes(Filters=[{"Name": "status", "Values": ["available"]}]).get(
            "Volumes", []
        )
    except ClientError:
        available_volumes = []
    try:
        # Snapshots you own; these incur storage charges until deleted.
        owned_snapshots = client.describe_snapshots(OwnerIds=["self"]).get("Snapshots", [])
    except ClientError:
        owned_snapshots = []

    for a in unassoc_eips:
        reporter({
            "phase": "PLAN",
            "service": "ec2",
            "region": region,
            "resource_type": "eip",
            "id": a.get("AllocationId") or a.get("PublicIp"),
            "name": a.get("PublicIp"),
            "action": "release",
            "status": "planned",
        })

    for v in available_volumes:
        reporter({
            "phase": "PLAN",
            "service": "ec2",
            "region": region,
            "resource_type": "volume",
            "id": v.get("VolumeId"),
            "name": _get_name_tag(v.get("Tags")),
            "action": "delete",
            "status": "planned",
        })

    for sn in owned_snapshots:
        reporter({
            "phase": "PLAN",
            "service": "ec2",
            "region": region,
            "resource_type": "snapshot",
            "id": sn.get("SnapshotId"),
            "name": _get_name_tag(sn.get("Tags")),
            "action": "delete",
            "status": "planned",
        })

    if dry_run:
        return 0

    # EXEC: terminate instances
    # This stops instance-hour charges. We record which instance IDs actually succeeded.
    deleted = 0
    terminated_iids: list[str] = []
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
            if iid:
                terminated_iids.append(iid)
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

    # EXEC: release the EIPs we planned that belong to the successfully terminated instances
    # Disassociate first (if any), then release by AllocationId (or PublicIp fallback).
    if terminated_iids:
        planned_eips_for_terminated = [a for a in eips if a.get("InstanceId") in set(terminated_iids)]
        for a in planned_eips_for_terminated:
            ident = {"id": a.get("AllocationId") or a.get("PublicIp"), "name": a.get("PublicIp")}
            assoc_id = a.get("AssociationId")
            alloc_id = a.get("AllocationId")
            try:
                if assoc_id:
                    with contextlib.suppress(ClientError):
                        client.disassociate_address(AssociationId=assoc_id)
                if alloc_id:
                    client.release_address(AllocationId=alloc_id)
                else:
                    public_ip = a.get("PublicIp")
                    if public_ip:
                        client.release_address(PublicIp=public_ip)
                reporter({
                    "phase": "EXEC",
                    "service": "ec2",
                    "region": region,
                    "resource_type": "eip",
                    "action": "release",
                    "status": "success",
                    **ident,
                })
                deleted += 1
            except ClientError as e:
                reporter({
                    "phase": "EXEC",
                    "service": "ec2",
                    "region": region,
                    "resource_type": "eip",
                    "action": "release",
                    "status": "failed",
                    "reason": str(e),
                    **ident,
                })

    # EXEC: delete only volumes marked keep (may still be in-use; best-effort single attempt)
    # We refetch volumes for the successfully terminated instances and delete ones that opted out of auto-delete.
    if terminated_iids:
        try:
            vols_resp = client.describe_volumes(Filters=[{"Name": "attachment.instance-id", "Values": terminated_iids}])
            volumes_to_consider = vols_resp.get("Volumes", [])
        except ClientError:
            volumes_to_consider = []

        attempted_volume_ids: set[str] = set()
        for v in volumes_to_consider:
            if not _volume_marked_keep(v):
                continue
            vid = v.get("VolumeId")
            try:
                client.delete_volume(VolumeId=vid)
                reporter({
                    "phase": "EXEC",
                    "service": "ec2",
                    "region": region,
                    "resource_type": "volume",
                    "id": vid,
                    "action": "delete",
                    "status": "success",
                })
                deleted += 1
            except ClientError as e:
                reporter({
                    "phase": "EXEC",
                    "service": "ec2",
                    "region": region,
                    "resource_type": "volume",
                    "id": vid,
                    "action": "delete",
                    "status": "failed",
                    "reason": str(e),
                })
            if vid:
                attempted_volume_ids.add(vid)

    # EXEC: release any unassociated EIPs (final sweep)
    # Avoid idle EIP charges unrelated to the instances above.
    for a in unassoc_eips:
        ident = {"id": a.get("AllocationId") or a.get("PublicIp"), "name": a.get("PublicIp")}
        try:
            alloc_id = a.get("AllocationId")
            if alloc_id:
                client.release_address(AllocationId=alloc_id)
            else:
                public_ip = a.get("PublicIp")
                if public_ip:
                    client.release_address(PublicIp=public_ip)
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "eip",
                "action": "release",
                "status": "success",
                **ident,
            })
            deleted += 1
        except ClientError as e:
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "eip",
                "action": "release",
                "status": "failed",
                "reason": str(e),
                **ident,
            })

    # EXEC: delete all remaining available volumes (final sweep)
    # Skip volumes we already tried (keep-volumes). Otherwise, remove detached volumes to avoid storage charges.
    attempted_volume_ids = locals().get("attempted_volume_ids", set())
    for v in available_volumes:
        vid = v.get("VolumeId")
        if not vid or vid in attempted_volume_ids:
            continue
        try:
            client.delete_volume(VolumeId=vid)
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "volume",
                "id": vid,
                "action": "delete",
                "status": "success",
            })
            deleted += 1
        except ClientError as e:
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "volume",
                "id": vid,
                "action": "delete",
                "status": "failed",
                "reason": str(e),
            })

    # EXEC: delete self-owned snapshots (final sweep)
    # Snapshots are charged per-GB-month; delete if you don't need them anymore.
    for sn in owned_snapshots:
        sid = sn.get("SnapshotId")
        if not sid:
            continue
        try:
            client.delete_snapshot(SnapshotId=sid)
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "snapshot",
                "id": sid,
                "action": "delete",
                "status": "success",
            })
            deleted += 1
        except ClientError as e:
            reporter({
                "phase": "EXEC",
                "service": "ec2",
                "region": region,
                "resource_type": "snapshot",
                "id": sid,
                "action": "delete",
                "status": "failed",
                "reason": str(e),
            })

    return deleted
