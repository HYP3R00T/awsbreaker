from types import SimpleNamespace

from costcutter.services.s3 import buckets


class DummyClientNonVersioned:
    def get_paginator(self, name):
        class P:
            def paginate(self, **kwargs):
                yield {"Contents": [{"Key": "foo.txt"}, {"Key": "bar.txt"}]}

        return P()


class DummyClientVersioned:
    def get_paginator(self, name):
        class P:
            def paginate(self, **kwargs):
                # return a page with Versions and DeleteMarkers
                yield {
                    "Versions": [{"Key": "v1.txt", "VersionId": "111"}],
                    "DeleteMarkers": [{"Key": "v2.txt", "VersionId": "222"}],
                }

        return P()


def test_catalog_objects_non_versioned():
    client = DummyClientNonVersioned()
    objs = buckets.catalog_objects(client=client, bucket_name="b", region="r")
    assert any(o["Key"] == "foo.txt" for o in objs)
    assert all("VersionId" in o for o in objs)


def test_catalog_objects_versioned():
    client = DummyClientVersioned()
    objs = buckets.catalog_objects(client=client, bucket_name="b", region="r")
    # should include both versions and delete markers with VersionId
    keys = {o["Key"] for o in objs}
    assert "v1.txt" in keys and "v2.txt" in keys
    assert all(o.get("VersionId") for o in objs)


def test_cleanup_objects_records_and_calls(monkeypatch):
    recorded = []

    class DummyReporter:
        def record(self, *a, **k):
            recorded.append((a, k))

    # Client that records last delete_objects payload
    last = {}

    class DummyClient:
        def delete_objects(self, **kwargs):
            last.update(kwargs)
            return {"Deleted": kwargs["Delete"]["Objects"]}

    monkeypatch.setattr("costcutter.services.s3.buckets.get_reporter", lambda: DummyReporter())
    client = DummyClient()
    objs = [{"Key": "a.txt", "VersionId": "1"}, {"Key": "b.txt", "VersionId": None}]
    # call the batched deleter directly
    buckets.cleanup_objects(
        client=client, bucket_name="buck", objects_iter=iter(objs), region="r", reporter=buckets.get_reporter()
    )

    # reporter recorded two events
    assert len(recorded) == 2
    # client.delete_objects invoked with Objects; the second entry should omit VersionId when None
    assert last["Bucket"] == "buck"
    assert isinstance(last["Delete"], dict)
    expected = [{"Key": "a.txt", "VersionId": "1"}, {"Key": "b.txt"}]
    assert last["Delete"]["Objects"] == expected


def test_delete_errors_are_recorded(monkeypatch):
    recorded = []

    class DummyReporter:
        def record(self, *a, **k):
            recorded.append((a, k))

    # Client that returns an Errors list for delete_objects
    last = {}

    class DummyClient:
        def delete_objects(self, **kwargs):
            last.update(kwargs)
            return {"Deleted": [], "Errors": [{"Key": "x.txt", "Code": "AccessDenied", "Message": "denied"}]}

    monkeypatch.setattr("costcutter.services.s3.buckets.get_reporter", lambda: DummyReporter())
    client = DummyClient()
    objs = [{"Key": "x.txt", "VersionId": None}]
    # call the batched deleter directly
    buckets.cleanup_objects(
        client=client, bucket_name="buck", objects_iter=iter(objs), region="r", reporter=buckets.get_reporter()
    )

    # Should have recorded the initial delete record and then a failure record
    assert len(recorded) >= 2
    # last delete payload should include the object (without VersionId)
    assert last["Delete"]["Objects"] == [{"Key": "x.txt"}]


def test_catalog_buckets_and_cleanup_buckets(monkeypatch):
    # Dummy session to return client with list_buckets
    class DummySession:
        def client(self, service_name=None, region_name=None):
            class C:
                def list_buckets(self):
                    return {"Buckets": [{"Name": "one"}, {"Name": "two"}]}

                def list_objects_v2(self, **kwargs):
                    return {"KeyCount": 0}

                def delete_bucket(self, **kwargs):
                    return {}

            return C()

    session = DummySession()
    names = buckets.catalog_buckets(session, "r")
    assert "one" in names and "two" in names

    # monkeypatch cleanup_bucket so cleanup_buckets runs quickly
    monkeypatch.setattr("costcutter.services.s3.buckets.cleanup_bucket", lambda *a, **k: None)
    buckets.cleanup_buckets(session=session, region="r", dry_run=True, max_workers=1)


def test_cleanup_bucket_dry_run(monkeypatch):
    class DummySession:
        def client(self, service_name=None, region_name=None):
            class C:
                def list_buckets(self):
                    return {"Buckets": []}

                def list_objects_v2(self, **kwargs):
                    return {"KeyCount": 0}

            return C()

    # ensure reporter.record is callable
    monkeypatch.setattr(
        "costcutter.services.s3.buckets.get_reporter", lambda: SimpleNamespace(record=lambda *a, **k: None)
    )
    buckets.cleanup_bucket(session=DummySession(), region="r", bucket_name="b", dry_run=True)
