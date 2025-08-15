import logging
from typing import Any

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def run(session: Any, region: str, dry_run: bool, reporter) -> int:
    client = session.client("lambda", region_name=region)

    # PLAN: list functions
    functions: list[dict[str, Any]] = []
    try:
        paginator = client.get_paginator("list_functions")
        for page in paginator.paginate():
            functions.extend(page.get("Functions", []))
    except ClientError as e:
        logger.error("[%s][lambda] Failed to list Lambda functions: %s", region, e)
        functions = []

    for fn in functions:
        name = fn.get("FunctionName") or fn.get("FunctionArn")
        reporter({
            "phase": "PLAN",
            "service": "lambda",
            "region": region,
            "resource_type": "function",
            "id": name,
            "name": fn.get("FunctionName"),
            "action": "delete",
            "status": "planned",
            "extra": {"runtime": fn.get("Runtime"), "version": fn.get("Version")},
        })

    if dry_run:
        return 0

    # EXECUTE: delete functions
    deleted = 0
    for fn in functions:
        name = fn.get("FunctionName") or fn.get("FunctionArn")
        if not name:
            continue
        try:
            client.delete_function(FunctionName=name)
            reporter({
                "phase": "EXEC",
                "service": "lambda",
                "region": region,
                "resource_type": "function",
                "id": name,
                "action": "delete",
                "status": "success",
            })
            deleted += 1
        except ClientError as e:
            reporter({
                "phase": "EXEC",
                "service": "lambda",
                "region": region,
                "resource_type": "function",
                "id": name or "?",
                "action": "delete",
                "status": "failed",
                "reason": str(e),
            })

    return deleted
