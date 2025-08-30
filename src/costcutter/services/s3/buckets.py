import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from costcutter.reporter import get_reporter

SERVICE: str = "s3"
RESOURCE: str = "buckets"
logger = logging.getLogger(__name__)


def catalog_top_level_objects(client: Any, bucket_name: str, region: str) -> list[dict[str, str | None]]:
    objects_to_delete: list[dict[str, str | None]] = []
    try:
        # List object versions first; include DeleteMarkers so VersionId deletions work.
        paginator = client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket_name, Prefix=""):
            # "Versions" contains actual object versions
            if "Versions" in page:
                objects_to_delete.extend([{"Key": v["Key"], "VersionId": v.get("VersionId")} for v in page["Versions"]])
            # "DeleteMarkers" contains delete markers (also need VersionId)
            if "DeleteMarkers" in page:
                objects_to_delete.extend([
                    {"Key": d["Key"], "VersionId": d.get("VersionId")} for d in page["DeleteMarkers"]
                ])
        # Fall back to list_objects_v2 for non-versioned buckets (no VersionId).
        if not objects_to_delete:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name, Prefix=""):
                if "Contents" in page:
                    objects_to_delete.extend([{"Key": obj["Key"], "VersionId": None} for obj in page["Contents"]])
        logger.info(
            "[%s][s3] catalog_top_level_objects: found %d objects for bucket=%s",
            region,
            len(objects_to_delete),
            bucket_name,
        )
    except ClientError as e:
        logger.exception("[%s][s3] Failed to list objects/versions: %s", region, e)
        objects_to_delete = []
    return objects_to_delete


def cleanup_top_level_objects(
    client: Any, bucket_name: str, objects_to_delete: list[dict[str, str | None]], region: str
):
    reporter = get_reporter()
    action = "delete"
    status = "executing"
    # Record an individual report for each object (use full object ARN)
    logger.info(
        "[%s][s3] cleanup_top_level_objects: preparing to delete %d objects from bucket=%s",
        region,
        len(objects_to_delete),
        bucket_name,
    )
    # Record each object's ARN (meta includes VersionId when present).
    for obj in objects_to_delete:
        key = obj.get("Key")
        if not key:
            # skip malformed entries
            continue
        version_id = obj.get("VersionId")
        obj_arn = f"arn:aws:s3:::{bucket_name}/{key}"
        # include version id in metadata so reports can reference exact version
        meta = {"status": status, "key": key}
        if version_id:
            meta["version_id"] = version_id
        reporter.record(
            region,
            SERVICE,
            "object",
            action,
            arn=obj_arn,
            meta=meta,
        )
    try:
        # delete_objects accepts per-object VersionId; check Deleted/Errors.
        response = client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects_to_delete, "Quiet": False})
        logger.info(
            "[%s][s3] cleanup_top_level_objects: delete_objects response Deleted=%s",
            region,
            response.get("Deleted", []),
        )
        if "Errors" in response:
            logger.error(
                "[%s][s3] cleanup_top_level_objects: delete_objects reported errors=%s", region, response["Errors"]
            )
    except ClientError as e:
        logger.exception("[%s][s3] cleanup_top_level_objects: Error deleting objects: %s", region, e)


def catalog_buckets(session: Session, region: str) -> list[str]:
    # Use an S3 client without a forced region to list and query bucket locations.
    client = session.client(service_name="s3")

    bucket_names: list[str] = []
    try:
        resp = client.list_buckets()
        buckets = resp.get("Buckets", [])
        for b in buckets:
            name = b.get("Name")
            if not name:
                continue
            try:
                loc = client.get_bucket_location(Bucket=name).get("LocationConstraint")
                # AWS returns None for us-east-1
                bucket_region = loc or "us-east-1"
            except ClientError as e:
                logger.warning("[%s][s3] could not get location for bucket=%s: %s", region, name, e)
                continue
            # include bucket only if its location matches the requested region
            if bucket_region == region:
                bucket_names.append(name)
        logger.info("[%s][s3] catalog_buckets: discovered %d buckets in region %s", region, len(bucket_names), region)
    except ClientError as e:
        logger.exception("[%s][s3] Failed to list buckets: %s", region, e)
        bucket_names = []
    return bucket_names


def cleanup_bucket(session: Session, region: str, bucket_name: str, dry_run: bool = True) -> None:
    reporter = get_reporter()
    action = "catalog" if dry_run else "delete"
    status = "discovered" if dry_run else "executing"
    # account id not needed for S3 bucket ARN
    # Construct proper ARN for the instance resource
    arn = f"arn:aws:s3:::{bucket_name}"
    reporter.record(
        region,
        SERVICE,
        RESOURCE,
        action,
        arn=arn,
        meta={"status": status, "dry_run": dry_run},
    )

    # S3 ARNs omit account id; region is used for logging.
    if dry_run:
        logger.info("[%s][s3][bucket] dry-run: would process bucket=%s", region, bucket_name)
        return
    try:
        client = session.client("s3", region_name=region)
        # Determine top-level objects (handles versioned and non-versioned buckets)
        objects_to_delete: list[dict[str, str]] = catalog_top_level_objects(
            client=client, bucket_name=bucket_name, region=region
        )
        if objects_to_delete:
            logger.info(
                "[%s][s3][bucket] found %d objects to delete for bucket=%s",
                region,
                len(objects_to_delete),
                bucket_name,
            )
            cleanup_top_level_objects(
                client=client, bucket_name=bucket_name, objects_to_delete=objects_to_delete, region=region
            )
        else:
            logger.info("[%s][s3][bucket] no objects to delete for bucket=%s", region, bucket_name)

        client.delete_bucket(Bucket=bucket_name)
        logger.info("[%s][s3][bucket] delete requested bucket=%s", region, bucket_name)
        reporter.record(
            region,
            SERVICE,
            RESOURCE,
            "delete",
            arn=arn,
            meta={"status": "executing", "dry_run": dry_run},
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code") if hasattr(e, "response") else None
        if dry_run and code == "DryRunOperation":
            logger.info("[%s][ec2][key_pair] dry-run delete would succeed bucket_name=%s", region, bucket_name)
        else:
            logger.error("[%s][s3][bucket] delete failed bucket_name=%s error=%s", region, bucket_name, e)
            # keep existing log line for backward compatibility (copied message)
            logger.error("[%s][ec2][key_pair] delete failed bucket_name=%s error=%s", region, bucket_name, e)


def cleanup_buckets(session: Session, region: str, dry_run: bool = True, max_workers: int = 1) -> None:
    bucket_names: list[str] = catalog_buckets(session=session, region=region)
    logger.info("[%s][s3] cleanup_buckets: buckets to process (%d)=%s", region, len(bucket_names), bucket_names)
    # Process buckets concurrently; tune `max_workers` as needed.
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(cleanup_bucket, session, region, bucket_name, dry_run) for bucket_name in bucket_names]
        for fut in as_completed(futures):
            # propagate exceptions from worker threads to the caller
            fut.result()
