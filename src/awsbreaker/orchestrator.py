import inspect
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from boto3.session import Session

from awsbreaker.conf.config import get_config
from awsbreaker.core.session_helper import create_aws_session

# Reporter no longer needed at service-level (resource handlers still record events)
from awsbreaker.services.ec2 import cleanup_ec2

logger = logging.getLogger(__name__)

SERVICE_HANDLERS = {
    # Each value can be a functional entrypoint `run(session, region, dry_run, reporter)`
    "ec2": cleanup_ec2,
    # "s3": cleanup_s3
    # "lambda": cleanup_lambda,
}


def _service_supported_in_region(available_regions_map: dict[str, set[str]], service_key: str, region: str) -> bool:
    regions = available_regions_map.get(service_key)
    # If mapping unknown, default to allowed to avoid over-blocking
    return True if regions is None else region in regions


def process_region_service(
    session: Session,
    region: str,
    service_key: str,
    handler_entry: Callable,
    dry_run: bool,
) -> None:
    logger.info("[%s][%s] Starting (dry_run=%s)", region, service_key, dry_run)

    # Updated functional entrypoint: run(session, region, dry_run, **kwargs?) -> int|None
    # NOTE: Service-level reporter events removed to reduce output volume; resource-level handlers still record.
    if inspect.isfunction(handler_entry):
        try:
            logger.info("[%s][%s] Executing service handler", region, service_key)
            handler_entry(session=session, region=region, dry_run=dry_run)
        except Exception as e:
            logger.exception("[%s][%s] Failed: %s", region, service_key, e)
            raise
        else:
            logger.info("[%s][%s] Finished", region, service_key)
        return

    raise TypeError(f"Unsupported handler type for service '{service_key}': {type(handler_entry)!r}")


def orchestrate_services(
    dry_run: bool = False,
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

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map: dict[Any, tuple[str, str]] = {}
        for region, service_key, handler_entry in tasks:
            fut = executor.submit(process_region_service, session, region, service_key, handler_entry, dry_run)
            future_map[fut] = (region, service_key)

        for future in as_completed(future_map):
            region, svc_name = future_map[future]
            try:
                logger.info("[%s][%s] Task completed", region, svc_name)
            except Exception as e:
                logger.exception("[%s][%s] Task failed: %s", region, svc_name, e)
