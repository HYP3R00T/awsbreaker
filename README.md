# AWSBreaker

> [!CAUTION]
> AWSBreaker will delete AWS resources aggressively and indiscriminately once triggered.
> This tool is designed for **students and experimenters** who are worried about accidental AWS costs.

AWSBreaker is an **automated kill-switch for AWS accounts**.
It monitors **AWS Budgets**, and when costs exceed predefined limits, it triggers automated cleanup of AWS resources to prevent unexpected charges.

## 🎯 Project Objectives

- **Primary Goal**: Prevent unexpected AWS bills by automatically cleaning up resources once a cost budget threshold is breached.
- **Approach**:
  - Monitor costs using AWS Budgets.
  - Trigger alerts via SNS when budget crosses threshold.
  - Automated cleanup using a Python-based AWS Lambda function (boto3).
  - Fully serverless & free-tier friendly (Lambda, SNS, Budgets only).
