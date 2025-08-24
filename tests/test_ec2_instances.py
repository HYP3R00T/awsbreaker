from awsbreaker.services.ec2 import instances


class DummySession:
    def client(self, service_name=None, region_name=None):
        class Client:
            def get_caller_identity(self):
                return {"Account": "123456789012"}

            def describe_instances(self):
                return {"Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]}

            def terminate_instances(self, **kwargs):
                return {
                    "TerminatingInstances": [
                        {
                            "InstanceId": "i-123",
                            "CurrentState": {"Name": "running"},
                            "PreviousState": {"Name": "stopped"},
                        }
                    ]
                }

        return Client()


def test_get_account_id():
    session = DummySession()
    assert instances._get_account_id(session) == "123456789012"


def test_catalog_instances():
    session = DummySession()
    arns = instances.catalog_instances(session, "us-east-1")
    assert "i-123" in arns


def test_cleanup_instance(monkeypatch):
    session = DummySession()
    monkeypatch.setattr(
        "awsbreaker.services.ec2.instances.get_reporter", lambda: type("R", (), {"record": lambda *a, **k: None})()
    )
    instances.cleanup_instance(session, "us-east-1", "i-123", dry_run=True)


def test_cleanup_instances(monkeypatch):
    session = DummySession()
    monkeypatch.setattr("awsbreaker.services.ec2.instances.catalog_instances", lambda *args, **kwargs: ["i-123"])
    monkeypatch.setattr("awsbreaker.services.ec2.instances.cleanup_instance", lambda *args, **kwargs: None)
    instances.cleanup_instances(session, "us-east-1", dry_run=True, max_workers=1)
