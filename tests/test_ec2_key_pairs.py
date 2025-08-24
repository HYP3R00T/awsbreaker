from awsbreaker.services.ec2 import key_pairs


class DummySession:
    def client(self, service_name=None, region_name=None):
        class Client:
            def get_caller_identity(self):
                return {"Account": "123456789012"}

            def describe_key_pairs(self):
                return {"KeyPairs": [{"KeyPairId": "kp-123"}]}

            def delete_key_pair(self, **kwargs):
                return {"KeyPairId": "kp-123", "Return": True}

        return Client()


def test_get_account_id():
    session = DummySession()
    assert key_pairs._get_account_id(session) == "123456789012"


def test_catalog_key_pairs():
    session = DummySession()
    arns = key_pairs.catalog_key_pairs(session, "us-east-1")
    assert "kp-123" in arns


def test_cleanup_key_pair(monkeypatch):
    session = DummySession()
    monkeypatch.setattr(
        "awsbreaker.services.ec2.key_pairs.get_reporter", lambda: type("R", (), {"record": lambda *a, **k: None})()
    )
    key_pairs.cleanup_key_pair(session, "us-east-1", "kp-123", dry_run=True)


def test_cleanup_key_pairs(monkeypatch):
    session = DummySession()
    monkeypatch.setattr("awsbreaker.services.ec2.key_pairs.catalog_key_pairs", lambda *args, **kwargs: ["kp-123"])
    monkeypatch.setattr("awsbreaker.services.ec2.key_pairs.cleanup_key_pair", lambda *args, **kwargs: None)
    key_pairs.cleanup_key_pairs(session, "us-east-1", dry_run=True, max_workers=1)
