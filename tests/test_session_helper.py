import logging
import os

import pytest

from awsbreaker.conf.config import Config
from awsbreaker.core import session_helper


class DummySession:
    pass


def _fake_session_factory(captured: dict):
    def _factory(*args, **kwargs):  # boto3.Session is called with kwargs in our code
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummySession()

    return _factory


def test_create_session_with_explicit_keys(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    cfg = Config({
        "aws": {
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "SECRET",
            "aws_session_token": "TOKEN",
            "region": ["us-west-2"],
        }
    })

    captured: dict = {}
    monkeypatch.setattr(session_helper.boto3, "Session", _fake_session_factory(captured))

    with caplog.at_level(logging.INFO, logger=session_helper.__name__):
        sess = session_helper.create_aws_session(cfg)

    assert isinstance(sess, DummySession)
    assert captured["args"] == ()
    assert captured["kwargs"] == {
        "aws_access_key_id": "AKIA_TEST",
        "aws_secret_access_key": "SECRET",
        "aws_session_token": "TOKEN",
    }
    assert "Using credentials from config (access key + secret)" in "\n".join(caplog.messages)
    assert os.environ.get("AWS_SHARED_CREDENTIALS_FILE") is None


def test_create_session_with_credentials_file(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    path = os.path.expanduser("~/fake/.aws/alt_credentials")
    cfg = Config({
        "aws": {
            "credential_file_path": "~/fake/.aws/alt_credentials",
            "profile": "dev",
            "region": ["eu-central-1"],
        }
    })

    captured: dict = {}
    monkeypatch.setattr(session_helper.boto3, "Session", _fake_session_factory(captured))
    monkeypatch.setattr(session_helper.os.path, "isfile", lambda p: p == path)

    # ensure clean env to observe setenv behavior
    monkeypatch.delenv("AWS_SHARED_CREDENTIALS_FILE", raising=False)

    with caplog.at_level(logging.INFO, logger=session_helper.__name__):
        sess = session_helper.create_aws_session(cfg)

    assert isinstance(sess, DummySession)
    assert captured["args"] == ()
    assert captured["kwargs"] == {"profile_name": "dev"}
    assert os.environ.get("AWS_SHARED_CREDENTIALS_FILE") == path
    assert f"Using credentials file at {path} with profile 'dev'" in "\n".join(caplog.messages)


def test_create_session_defaults_when_no_credentials(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    cfg = Config({"aws": {"region": ["ap-southeast-1"]}})

    captured: dict = {}
    monkeypatch.setattr(session_helper.boto3, "Session", _fake_session_factory(captured))
    # ensure file path branch is not taken
    monkeypatch.setattr(session_helper.os.path, "isfile", lambda p: False)

    with caplog.at_level(logging.INFO, logger=session_helper.__name__):
        sess = session_helper.create_aws_session(cfg)

    assert isinstance(sess, DummySession)
    assert captured["kwargs"] == {}
    assert "Using default boto3 session (env vars, ~/.aws/credentials, etc.)" in "\n".join(caplog.messages)


def test_create_session_when_config_missing_aws(monkeypatch: pytest.MonkeyPatch):
    cfg = Config({})  # no 'aws' attribute present -> triggers AttributeError path

    captured: dict = {}
    monkeypatch.setattr(session_helper.boto3, "Session", _fake_session_factory(captured))
    # default branch, ensure no creds file
    monkeypatch.setattr(session_helper.os.path, "isfile", lambda p: False)

    sess = session_helper.create_aws_session(cfg)

    assert isinstance(sess, DummySession)
    assert "region" not in captured["kwargs"]
