from pathlib import Path

from awsbreaker.reporter import Reporter


def test_reporter_write_csv(tmp_path: Path):
    r = Reporter()
    r.record(
        region="us-east-1",
        service="ec2",
        resource="instance",
        action="terminate",
        arn="arn:aws:ec2:123",
        meta={"id": 1},
    )
    r.record(region="ap-south-1", service="ec2", resource="key-pair", action="delete", arn=None, meta={"name": "kp"})

    out_file = tmp_path / "events.csv"
    written = r.write_csv(out_file)

    assert written.exists()
    content = written.read_text().strip().splitlines()
    # header + 2 rows
    assert len(content) == 3
    header = content[0].split(",")
    assert header == ["timestamp", "region", "service", "resource", "action", "arn", "meta"]

    # append mode
    r.record(
        region="us-east-1",
        service="ec2",
        resource="instance",
        action="terminate",
        arn="arn:aws:ec2:456",
        meta={"id": 2},
    )
    r.write_csv(out_file, overwrite=False)
    content2 = out_file.read_text().strip().splitlines()
    assert len(content2) == 4  # one more row, header not duplicated
