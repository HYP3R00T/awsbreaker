# awsbreaker CLI Usage Guide

This guide explains how to use the awsbreaker command-line interface (CLI), including available flags and usage examples.

## Running the CLI

You can run the CLI using Python:

```zsh
python -m awsbreaker.cli [OPTIONS]
```
Or, if installed as a package:
```zsh
awsbreaker [OPTIONS]
```

## Common Flags and Options

| Flag / Option           | Description                                                      |
|------------------------|------------------------------------------------------------------|
| `--help`               | Show help message and exit.                                      |
| `--dry-run`            | Simulate actions without making changes to AWS resources.         |
| `--config PATH`        | Specify a custom config file path.  |

## Example Usage

- **Show help:**
  ```zsh
  python -m awsbreaker.cli --help
  ```

**Run in dry-run mode:**
  ```zsh
  python -m awsbreaker.cli --dry-run
  ```

**Specify config file:**
  ```zsh
  python -m awsbreaker.cli --config /path/to/config.yaml
  ```

## Notes

- Only `--dry-run` and `--config` are supported as CLI flags.
- All other configuration (regions, services, logging, reporting, etc.) must be set in the config file (`src/awsbreaker/conf/config.yaml`).
- For a full list of options, run:
  ```zsh
  python -m awsbreaker.cli --help
  ```

---

For more details, see the main documentation or source code in `src/awsbreaker/cli.py`.
