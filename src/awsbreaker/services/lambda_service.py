import logging
from typing import Any

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _report(
    reporter,
    *,
    region: str,
    phase: str,
    resource_type: str,
    ident: dict[str, Any],
    status: str,
    action: str = "delete",
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "phase": phase,
        "service": "lambda",
        "region": region,
        "resource_type": resource_type,
        "action": action,
        "status": status,
        **ident,
    }
    if extra:
        payload["extra"] = extra
    reporter(payload)


def _list_functions(lambda_client) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        functions.extend(page.get("Functions", []) or [])
    return functions


def _list_event_source_mapping_ids(lambda_client, function_name: str) -> list[str]:
    ids: list[str] = []
    marker: str | None = None
    while True:
        kwargs: dict[str, Any] = {"FunctionName": function_name}
        if marker:
            kwargs["Marker"] = marker
        resp = lambda_client.list_event_source_mappings(**kwargs)
        ids.extend([m.get("UUID") for m in (resp.get("EventSourceMappings", []) or []) if m.get("UUID")])
        marker = resp.get("NextMarker")
        if not marker:
            break
    return ids


def run(session: Any, region: str, dry_run: bool, reporter) -> int:
    """Plan and delete Lambda functions with minimal, high-impact extras.

    Kept intentionally small and cheap, mirroring EC2 scope choices:
    - Functions: plan + delete (DeleteFunction removes all versions & aliases)
    - Event source mappings: plan + delete (prevents async invocations, reduces noise)
    - Default CloudWatch log groups: plan + delete (stops log storage charges)
    """
    lambda_client = session.client("lambda", region_name=region)
    logs_client = session.client("logs", region_name=region)

    # PLAN: functions and related (single pass; cache ESM IDs for exec)
    try:
        functions = _list_functions(lambda_client)
    except ClientError as e:
        logger.error("[%s][lambda] Failed to list Lambda functions: %s", region, e)
        functions = []

    esm_index: dict[str, list[str]] = {}
    log_groups: list[str] = []

    for fn in functions:
        fname = fn.get("FunctionName")
        fid = fname or fn.get("FunctionArn")
        _report(
            reporter,
            region=region,
            phase="PLAN",
            resource_type="function",
            ident={"id": fid, "name": fname},
            status="planned",
            extra={"runtime": fn.get("Runtime"), "version": fn.get("Version")},
        )

        if not fname:
            continue
        # ESMs
        try:
            ids = _list_event_source_mapping_ids(lambda_client, fname)
        except ClientError:
            ids = []
        esm_index[fname] = ids
        for mid in ids:
            _report(
                reporter,
                region=region,
                phase="PLAN",
                resource_type="event_source_mapping",
                ident={"id": mid, "name": mid},
                status="planned",
            )
        # Log group
        lg = f"/aws/lambda/{fname}"
        log_groups.append(lg)
        _report(
            reporter,
            region=region,
            phase="PLAN",
            resource_type="log_group",
            ident={"id": lg, "name": fname},
            status="planned",
        )

    if dry_run:
        return 0

    # EXECUTE
    deleted = 0

    for fn in functions:
        fname = fn.get("FunctionName")
        fid = fname or fn.get("FunctionArn") or "?"

        # Delete cached ESMs first (best-effort, no extra listing)
        for mid in esm_index.get(fname or "", []):
            try:
                lambda_client.delete_event_source_mapping(UUID=mid)
                _report(
                    reporter,
                    region=region,
                    phase="EXEC",
                    resource_type="event_source_mapping",
                    ident={"id": mid},
                    status="success",
                )
                deleted += 1
            except ClientError as e:
                _report(
                    reporter,
                    region=region,
                    phase="EXEC",
                    resource_type="event_source_mapping",
                    ident={"id": mid},
                    status="failed",
                    extra={"reason": str(e)},
                )

        # Delete function (removes all versions & aliases)
        try:
            lambda_client.delete_function(FunctionName=fname or fid)
            _report(
                reporter,
                region=region,
                phase="EXEC",
                resource_type="function",
                ident={"id": fid},
                status="success",
            )
            deleted += 1
        except ClientError as e:
            _report(
                reporter,
                region=region,
                phase="EXEC",
                resource_type="function",
                ident={"id": fid},
                status="failed",
                extra={"reason": str(e)},
            )

        # Delete default log group (best-effort)
        if fname:
            lg_name = f"/aws/lambda/{fname}"
            try:
                logs_client.delete_log_group(logGroupName=lg_name)
                _report(
                    reporter,
                    region=region,
                    phase="EXEC",
                    resource_type="log_group",
                    ident={"id": lg_name},
                    status="success",
                )
                deleted += 1
            except ClientError as e:
                _report(
                    reporter,
                    region=region,
                    phase="EXEC",
                    resource_type="log_group",
                    ident={"id": lg_name},
                    status="failed",
                    extra={"reason": str(e)},
                )

    return deleted
