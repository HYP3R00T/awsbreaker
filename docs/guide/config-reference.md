# Configuration Reference: config.yaml

This document explains the settings available in `src/awsbreaker/conf/config.yaml` for customizing awsbreaker behavior.

## Top-Level Options

### `dry_run`
- **Type:** boolean
- **Description:** If `true`, actions are simulated and no changes are made to AWS resources.

## Logging

### `logging.enabled`
- **Type:** boolean
- **Description:** Enable or disable logging.

### `logging.level`
- **Type:** string
- **Options:** `INFO`, `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`
- **Description:** Set the log verbosity.

### `logging.dir`
- **Type:** string (path)
- **Description:** Directory for log files.

## Reporting

### `reporting.csv.enabled`
- **Type:** boolean
- **Description:** Enable or disable CSV reporting.

### `reporting.csv.path`
- **Type:** string (path)
- **Description:** Path to save CSV reports.

## AWS Settings

### `aws.profile`
- **Type:** string
- **Description:** AWS CLI profile to use for authentication.

### `aws.aws_access_key_id`, `aws.aws_secret_access_key`, `aws.aws_session_token`
- **Type:** string
- **Description:** Directly specify AWS credentials. Leave empty to use credentials file.

### `aws.credential_file_path`
- **Type:** string (path)
- **Description:** Path to AWS credentials file (default: `~/.aws/credentials`).

### `aws.max_workers`
- **Type:** integer
- **Description:** Number of parallel workers for AWS operations.

### `aws.region`
- **Type:** list of strings
- **Description:** AWS regions to scan. Example: `us-east-1`, `ap-south-1`. Use `all` to scan all regions (WIP).

### `aws.services`
- **Type:** list of strings
- **Description:** AWS services to scan. Example: `ec2`, `lambda`. Use `all` to scan all services (WIP).

---

## Example

```yaml
dry_run: true
logging:
  enabled: false
  level: INFO
  dir: ~/.local/share/awsbreaker/logs
reporting:
  csv:
    enabled: false
    path: ~/.local/share/awsbreaker/reports/events.csv
aws:
  profile: default
  aws_access_key_id: ""
  aws_secret_access_key: ""
  aws_session_token: ""
  credential_file_path: ~/.aws/credentials
  max_workers: 4
  region:
    - us-east-1
    - ap-south-1
  services:
    - ec2
    - lambda
```

---

For more details, see inline comments in the config file or refer to the main documentation.
