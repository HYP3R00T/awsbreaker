from boto3.session import Session

from costcutter.services.s3.buckets import cleanup_buckets

_HANDLERS = {"buckets": cleanup_buckets}


def cleanup_s3(session: Session, region: str, dry_run: bool = True, max_workers: int = 1):
    # targets: list[str] or None => run all registered
    for fn in _HANDLERS.values():
        fn(session=session, region=region, dry_run=dry_run, max_workers=max_workers)
