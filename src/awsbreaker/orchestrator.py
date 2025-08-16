import inspect
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from awsbreaker.conf.config import get_config
from awsbreaker.core.session_helper import create_aws_session
from awsbreaker.services import ec2_service as ec2_service
from awsbreaker.services import lambda_service as lambda_service

logger = logging.getLogger(__name__)

SERVICE_HANDLERS = {
    # Each value can be a functional entrypoint `run(session, region, dry_run, reporter)`
    "ec2": ec2_service.run,
    "lambda": lambda_service.run,
    # Add other services here, e.g., "s3": s3_service.run
}


def _service_supported_in_region(available_regions_map: dict[str, set[str]], service_key: str, region: str) -> bool:
    regions = available_regions_map.get(service_key)
    # If mapping unknown, default to allowed to avoid over-blocking
    return True if regions is None else region in regions


def _make_reporter(region: str, service: str):
    """Create a reporter callable for consistent event logging across services.

    The reporter expects a dict event with keys like phase, resource_type, id, name, action, status, reason, extra.
    """

    def reporter(event: dict[str, Any]) -> None:
        phase = event.get("phase", "").upper()
        rtype = event.get("resource_type", "?")
        rid = event.get("id") or event.get("arn") or "?"
        name = event.get("name")
        action = event.get("action")
        status = event.get("status")
        reason = event.get("reason")
        extra = event.get("extra") or {}
        # Flatten a few extras into k=v for readability
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
        parts = [
            f"[{region}]",
            f"[{service}]",
            f"[{phase}]",
            f"[{rtype}]",
            f"id={rid}",
        ]
        if name:
            parts.append(f"name={name}")
        if action:
            parts.append(f"action={action}")
        if status:
            parts.append(f"status={status}")
        if reason:
            parts.append(f"reason={reason}")
        if extra_str:
            parts.append(extra_str)
        logger.info(" ".join(parts))

    return reporter


def process_region_service(
    session: Any,
    region: str,
    service_key: str,
    handler_entry: Any,
    dry_run: bool,
) -> tuple[str, str, int]:
    service_name = service_key
    logger.info("[%s][%s] Starting (dry_run=%s)", region, service_name, dry_run)

    # Functional entrypoint: run(session, region, dry_run, reporter) -> int (deletions)
    if inspect.isfunction(handler_entry):
        reporter = _make_reporter(region, service_name)
        try:
            logger.info("[%s][%s] Planning/Executing via functional entrypoint", region, service_name)
            deleted = handler_entry(session, region, dry_run, reporter)  # type: ignore[call-arg]
        except Exception as e:
            logger.exception("[%s][%s] Entrypoint failed: %s", region, service_name, e)
            raise
        logger.info("[%s][%s] Finished", region, service_name)
        return region, service_name, int(deleted or 0)

    # Legacy class-based handler support (for backward compatibility/testing)
    if inspect.isclass(handler_entry):
        handler = handler_entry(session, region, dry_run)
        logger.info("[%s][%s] Scanning", region, service_name)
        resources = handler.scan_resources()
        logger.info("[%s][%s] %d resource(s) found", region, service_name, len(resources))
        deleted = handler.delete_resources(resources)
        logger.info("[%s][%s] Finished", region, service_name)
        return region, service_name, int(deleted or 0)

    raise TypeError(f"Unsupported handler type for service '{service_key}': {type(handler_entry)!r}")


def orchestrate_services(
    dry_run: bool = False,
    progress_cb: Callable[[dict[str, int]], None] | None = None,
    print_summary: bool = True,
) -> dict[str, int]:
    config = get_config()

    # Resolve services
    selected_services_raw = list(getattr(config.aws, "services", []) or [])
    if not selected_services_raw:
        raise ValueError("No services configured under aws.services")
    if any(s.lower() == "all" for s in selected_services_raw):
        selected_service_keys = list(SERVICE_HANDLERS.keys())
    else:
        selected_service_keys = [s for s in selected_services_raw if s in SERVICE_HANDLERS]

    if not selected_service_keys:
        raise ValueError("No valid services selected in the configuration.")

    # Keep both key and handler together to avoid reverse lookups later
    services_to_process: list[tuple[str, Any]] = [(s, SERVICE_HANDLERS[s]) for s in selected_service_keys]

    # Create a base AWS session based on config/credentials
    session = create_aws_session(config)

    # Resolve regions
    regions_raw = list(getattr(config.aws, "region", []) or [])
    if not regions_raw:
        raise ValueError("No regions configured under aws.region")

    # Build a map of available regions for each selected service dynamically
    available_regions_map: dict[str, set[str]] = {}
    for svc_key in selected_service_keys:
        try:
            available = session.get_available_regions(svc_key)
        except Exception:
            # If boto3 cannot determine regions for a service key, leave it unknown
            available = []
        available_regions_map[svc_key] = set(available)

    if any(r.lower() == "all" for r in regions_raw):
        # Union of regions supported by selected services (dynamic)
        union: set[str] = set()
        for svc_key in selected_service_keys:
            union.update(available_regions_map.get(svc_key, set()))
        if not union:
            raise ValueError(
                "Unable to resolve regions for selected services. Specify explicit aws.region or ensure AWS SDK can list regions."
            )
        regions = sorted(union)
    else:
        regions = regions_raw

    logger.info("Regions to process: %s", regions)
    logger.info("Selected services: %s", selected_service_keys)
    logger.debug("Service handlers: %s", [h.__name__ for _, h in services_to_process])

    # Prebuild the work list and account for skips up front (still log skips)
    tasks: list[tuple[str, str, Any]] = []  # (region, service_key, handler_entry)
    skipped = 0
    for region in regions:
        for service_key, handler_entry in services_to_process:
            if not _service_supported_in_region(available_regions_map, service_key, region):
                logger.info("[%s][%s] Skipped: service not available in region", region, service_key)
                skipped += 1
                continue
            tasks.append((region, service_key, handler_entry))

    # Allow custom worker count via config, fallback to reasonable default based on actual tasks
    max_workers = getattr(getattr(config, "aws", None), "max_workers", None)
    if not isinstance(max_workers, int) or max_workers <= 0:
        total_tasks = max(1, len(tasks))
        max_workers = min(32, total_tasks)

    submitted = 0
    failures = 0
    deletions_total = 0
    succeeded = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map: dict[Any, tuple[str, str]] = {}
        for region, service_key, handler_entry in tasks:
            fut = executor.submit(process_region_service, session, region, service_key, handler_entry, dry_run)
            future_map[fut] = (region, service_key)
            submitted += 1

        # Initial progress update
        if progress_cb:
            progress_cb({
                "submitted": submitted,
                "skipped": skipped,
                "failures": failures,
                "succeeded": succeeded,
                "deletions": deletions_total,
                "completed": 0,
                "pending": len(future_map),
            })

        completed = 0
        for future in as_completed(future_map):
            region, svc_name = future_map[future]
            try:
                _region, _svc, deleted = future.result()
                deletions_total += deleted
                if deleted > 0:
                    succeeded += 1
                logger.info("[%s][%s] Task completed", region, svc_name)
            except Exception as e:
                failures += 1
                logger.exception("[%s][%s] Task failed: %s", region, svc_name, e)
            finally:
                completed += 1
                if progress_cb:
                    progress_cb({
                        "submitted": submitted,
                        "skipped": skipped,
                        "failures": failures,
                        "succeeded": succeeded,
                        "deletions": deletions_total,
                        "completed": completed,
                        "pending": max(0, len(future_map) - completed),
                    })

    return {
        "submitted": submitted,
        "skipped": skipped,
        "failures": failures,
        "succeeded": succeeded,
        "deletions": deletions_total,
    }
