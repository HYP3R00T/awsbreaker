import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session
from botocore.exceptions import ClientError

from costcutter.reporter import get_reporter

SERVICE: str = "s3"
RESOURCE: str = "buckets"
logger = logging.getLogger(__name__)


def catalog_objects(client: Any, bucket_name: str, region: str) -> Iterator[dict[str, str | None]]:
    """Stream top-level objects and versions for a bucket.

    Yields dicts with 'Key' and optional 'VersionId'. Does not accumulate all
    results in memory.
    """
    try:
        # List object versions first; include DeleteMarkers so VersionId deletions work.
        paginator = client.get_paginator("list_object_versions")
        any_versions = False
        for page in paginator.paginate(Bucket=bucket_name, Prefix=""):
            # "Versions" contains actual object versions
            if "Versions" in page:
                any_versions = True
                for v in page["Versions"]:
                    yield {"Key": v["Key"], "VersionId": v.get("VersionId")}
            # "DeleteMarkers" contains delete markers (also need VersionId)
            if "DeleteMarkers" in page:
                any_versions = True
                for d in page["DeleteMarkers"]:
                    yield {"Key": d["Key"], "VersionId": d.get("VersionId")}
        # Fall back to list_objects_v2 for non-versioned buckets (no VersionId).
        if not any_versions:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name, Prefix=""):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        yield {"Key": obj["Key"], "VersionId": None}
        logger.info(
            "[%s][s3] catalog_objects: finished streaming objects for bucket=%s",
            region,
            bucket_name,
        )
    except ClientError as e:
        logger.exception("[%s][s3] Failed to list objects/versions: %s", region, e)
        return


def abort_multipart_uploads(client: Any, bucket_name: str, region: str) -> int:
    """Abort any in-progress multipart uploads for the bucket."""
    aborted = 0
    try:
        paginator = client.get_paginator("list_multipart_uploads")
        for page in paginator.paginate(Bucket=bucket_name):
            uploads = page.get("Uploads", [])
            for up in uploads:
                key = up.get("Key")
                upload_id = up.get("UploadId")
                if not key or not upload_id:
                    continue
                try:
                    client.abort_multipart_upload(Bucket=bucket_name, Key=key, UploadId=upload_id)
                    aborted += 1
                except ClientError as e:
                    logger.warning(
                        "[%s][s3] abort_multipart_uploads: failed abort upload Key=%s UploadId=%s: %s",
                        region,
                        key,
                        upload_id,
                        e,
                    )
        logger.info("[%s][s3] abort_multipart_uploads: aborted %d uploads for bucket=%s", region, aborted, bucket_name)
    except ClientError as e:
        logger.exception("[%s][s3] Failed to list/abort multipart uploads: %s", region, e)
    return aborted


def cleanup_objects(
    client: Any, bucket_name: str, objects_iter: Iterator[dict[str, str | None]], region: str, reporter
) -> None:
    """Delete objects in batches of <=1000. Objects must be dicts with 'Key' and optional 'VersionId'."""
    batch: list[dict[str, str]] = []

    def _flush_batch():
        nonlocal batch
        if not batch:
            return
        try:
            response = client.delete_objects(Bucket=bucket_name, Delete={"Objects": batch, "Quiet": False})
            logger.info(
                "[%s][s3] cleanup_objects: delete_objects response Deleted=%s",
                region,
                response.get("Deleted", []),
            )
            if "Errors" in response:
                logger.error(
                    "[%s][s3] cleanup_objects: delete_objects reported errors=%s",
                    region,
                    response["Errors"],
                )
                # Record a failure event per errored object so reporter shows final status
                for err in response["Errors"]:
                    key = err.get("Key")
                    ver = err.get("VersionId")
                    code = err.get("Code")
                    message = err.get("Message")
                    obj_arn = f"arn:aws:s3:::{bucket_name}/{key}"
                    meta_fail = {"status": "failed", "key": key, "error_code": code, "error_message": message}
                    if ver:
                        meta_fail["version_id"] = ver
                    try:
                        reporter.record(region, SERVICE, "object", "delete", arn=obj_arn, meta=meta_fail)
                    except Exception:
                        # never fail the delete flow because reporting failed
                        logger.exception("[%s][s3] failed to record delete error for %s", region, key)
        except ClientError as e:
            logger.exception("[%s][s3] _delete_objects_in_batches: Error deleting objects: %s", region, e)
        batch = []

    for obj in objects_iter:
        key = obj.get("Key")
        if not key:
            continue
        version_id = obj.get("VersionId")
        # record each object's ARN (meta includes VersionId when present).
        obj_arn = f"arn:aws:s3:::{bucket_name}/{key}"
        meta = {"status": "executing", "key": key}
        if version_id:
            meta["version_id"] = version_id
        reporter.record(region, SERVICE, "object", "delete", arn=obj_arn, meta=meta)

        # build per-object delete entry; omit VersionId when None
        entry: dict[str, str] = {"Key": key}
        if version_id:
            entry["VersionId"] = version_id
        batch.append(entry)

        if len(batch) >= 1000:
            _flush_batch()

    # final flush
    _flush_batch()


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
                # Some test/dummy clients may not implement get_bucket_location.
                if not hasattr(client, "get_bucket_location"):
                    # assume the bucket is in the requested region
                    bucket_region = region
                else:
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
        # Abort any in-progress multipart uploads first
        abort_multipart_uploads(client=client, bucket_name=bucket_name, region=region)

        # Stream objects/versions and delete in batches to avoid memory blowup.
        objects_iter = catalog_objects(client=client, bucket_name=bucket_name, region=region)
        # Use the batched deleter which also records per-object reports.
        cleanup_objects(
            client=client, bucket_name=bucket_name, objects_iter=objects_iter, region=region, reporter=reporter
        )

        # Finally delete the bucket
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
