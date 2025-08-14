import logging
import os

import boto3
from boto3.session import Session

from awsbreaker.conf.config import Config

logger = logging.getLogger(__name__)


def create_aws_session(config: Config) -> Session:
    """Create a boto3 Session based on aws-related settings in Config.

    Falls back through explicit keys, credential file, then default discovery.
    """
    try:
        aws_config = config.aws
    except AttributeError:
        aws_config = Config({})

    aws_access_key_id = getattr(aws_config, "aws_access_key_id", None)
    aws_secret_access_key = getattr(aws_config, "aws_secret_access_key", None)
    aws_session_token = getattr(aws_config, "aws_session_token", None)
    credential_file_path = os.path.expanduser(getattr(aws_config, "credential_file_path", "") or "")
    profile_name = getattr(aws_config, "profile", "default")

    if aws_access_key_id and aws_secret_access_key:
        logger.info("Using credentials from config (access key + secret)")
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )
        return session

    if credential_file_path and os.path.isfile(credential_file_path):
        logger.info("Using credentials file at %s with profile '%s'", credential_file_path, profile_name)
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = credential_file_path
        session = boto3.Session(profile_name=profile_name)
        return session

    logger.info("Using default boto3 session (env vars, ~/.aws/credentials, etc.)")
    session = boto3.Session()
    return session
