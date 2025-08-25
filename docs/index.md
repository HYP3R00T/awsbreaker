---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "Cost Cutter"
  #   text: "A kill-switch for AWS"
  tagline: "A kill-switch for AWS"
  actions:
    - theme: brand
      text: What is CostCutter?
      link: /guide/what-is-costcutter
    - theme: alt
      text: Quickstart
      link: /config-reference
    - theme: alt
      text: GitHub
      link: https://github.com/HYP3R00T/costcutter

features:
  - icon: ⚡
    title: Fast AWS Resource Cleanup
    details: Scan and clean up EC2 instances, Lambda functions, and more with a single command. Supports dry-run mode for safe testing.
  - icon: 🛠️
    title: Configurable & Extensible
    details: Control regions, services, logging, and reporting via YAML config. Easily extend to new AWS services.
  - icon: 📊
    title: Live Event Reporting
    details: Real-time event table and summary with Rich UI. Export results to CSV for auditing and compliance.
  - icon: 🔒
    title: Secure Credential Handling
    details: Supports AWS profiles, environment variables, and credential files. No secrets stored in code.
---
