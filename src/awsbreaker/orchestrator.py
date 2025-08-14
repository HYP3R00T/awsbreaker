import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from awsbreaker.conf.config import get_config
from awsbreaker.core.session_helper import create_aws_session
from awsbreaker.services.ec2 import EC2ServiceHandler
from awsbreaker.services.lambda_service import LambdaServiceHandler

logger = logging.getLogger(__name__)

SERVICE_HANDLERS = {
    "ec2": EC2ServiceHandler,
    "lambda": LambdaServiceHandler,
    # Add other services here, e.g., "s3": S3ServiceHandler
}


def _service_supported_in_region(available_regions_map: dict[str, set[str]], service_key: str, region: str) -> bool:
    regions = available_regions_map.get(service_key)
    # If mapping unknown, default to allowed to avoid over-blocking
    return True if regions is None else region in regions


def process_region_service(
    session: Any,
    region: str,
    service_handler_cls: Callable[[Any, str, bool], Any],
    dry_run: bool,
) -> tuple[str, str, int]:
    service_name = service_handler_cls.__name__
    logger.info("[%s][%s] Starting (dry_run=%s)", region, service_name, dry_run)
    handler = service_handler_cls(session, region, dry_run)
    logger.info("[%s][%s] Scanning", region, service_name)
    resources = handler.scan_resources()
    logger.info("[%s][%s] %d resource(s) found", region, service_name, len(resources))
    deleted = handler.delete_resources(resources)
    logger.info("[%s][%s] Finished", region, service_name)
    return region, service_name, int(deleted or 0)


def orchestrate_services(dry_run: bool = False) -> None:
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

    services_to_process = [SERVICE_HANDLERS[s] for s in selected_service_keys]

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
    logger.debug("Service handlers: %s", [s.__name__ for s in services_to_process])

    # Allow custom worker count via config, fallback to reasonable default
    max_workers = getattr(getattr(config, "aws", None), "max_workers", None)
    if not isinstance(max_workers, int) or max_workers <= 0:
        # Cap to avoid too many threads; scale with task count
        total_tasks = max(1, len(regions) * len(services_to_process))
        max_workers = min(32, total_tasks)

    submitted = 0
    skipped = 0
    failures = 0
    deletions_total = 0
    succeeded = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map: dict[Any, tuple[str, str]] = {}
        for region in regions:
            for service_handler_cls in services_to_process:
                service_key = None
                # find key name for handler class for support check
                for k, v in SERVICE_HANDLERS.items():
                    if v is service_handler_cls:
                        service_key = k
                        break
                service_key = service_key or service_handler_cls.__name__

                if not _service_supported_in_region(available_regions_map, service_key, region):
                    logger.info("[%s][%s] Skipped: service not available in region", region, service_key)
                    skipped += 1
                    continue

                fut = executor.submit(process_region_service, session, region, service_handler_cls, dry_run)
                future_map[fut] = (region, service_handler_cls.__name__)
                submitted += 1

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

    # Here, "succeeded" means tasks that actually deleted at least one resource.
    # This excludes skipped tasks and no-op runs (e.g., nothing to delete or dry-run).
    print(
        f"Summary => submitted={submitted}, skipped={skipped}, failures={failures}, succeeded={succeeded}, deletions={deletions_total}"
    )
