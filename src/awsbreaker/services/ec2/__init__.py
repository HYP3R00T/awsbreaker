from boto3.session import Session

from awsbreaker.services.ec2.instances import cleanup_instances
from awsbreaker.services.ec2.key_pairs import cleanup_key_pairs

_HANDLERS = {"instances": cleanup_instances, "key_pairs": cleanup_key_pairs}


def cleanup_ec2(session: Session, region: str, dry_run: bool = True, max_workers: int = 1):
    # targets: list[str] or None => run all registered
    for fn in _HANDLERS.values():
        fn(session=session, region=region, dry_run=dry_run, max_workers=max_workers)
