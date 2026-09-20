# Sixth Street Take-Home — S3 + Lambda File Processor

An AWS CDK (Python) app that provisions an S3 bucket, a bucket policy, and a
Lambda that parses single-line files as they land in the bucket.

## Architecture

![Architecture diagram](docs/images/architecture.png)

A file uploaded to the S3 bucket triggers the Lambda via S3's native
`ObjectCreated` event notification (no queue or topic in between — a single
consumer with no fan-out doesn't need one). The Lambda reads the file back
via `GetObject`, splits its single line on commas, and logs the parsed
fields to CloudWatch. The bucket carries an explicit policy denying any
request that isn't using TLS (`aws:SecureTransport: false`).

**Assumption, stated plainly:** the assignment doesn't define the uploaded
file's format, so this assumes comma-separated values — the most common
plain-text convention. That assumption is documented in `lambda/handler.py`
and enforced nowhere else, so it's easy to change if the real format turns
out to be different.

## Repo layout

```
.
├── app.py                        # CDK app entrypoint
├── takehome_stack/
│   └── takehome_stack.py         # S3 bucket + policy + Lambda + event wiring
├── lambda/
│   └── handler.py                # the file-parsing logic
├── tests/unit/
│   ├── test_takehome_stack.py    # CDK synthesized-template assertions
│   └── test_handler.py           # Lambda logic unit tests (mocked S3)
└── .github/workflows/ci.yml      # runs tests + cdk synth on every push/PR
```

## Deploying

Requires the AWS CDK CLI and an AWS account with credentials configured
(`aws configure`, or an assumed role — this repo doesn't include or require
any stored credentials).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# One-time per AWS account/region:
cdk bootstrap

# Deploy:
cdk deploy
```

`cdk diff` before deploying shows exactly what would change. `cdk destroy`
tears the stack down (the bucket is configured to auto-delete its objects
and be removed with the stack, since this is a take-home, not a production
system holding data anyone needs to keep).

This stack was live-deployed and tested end-to-end against a real AWS
account during development: a normal comma-separated upload parsed
correctly, and an empty-file upload was logged as a clean error rather than
throwing — both matching the behavior asserted in the unit tests below.

## Running the tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

No AWS account or credentials are needed to run the tests or to run
`cdk synth` — the stack has no account/region-specific lookups, so both
work entirely offline. CI (`.github/workflows/ci.yml`) runs both on every
push and pull request.

## Maintaining this stack

- **Changing the parsing logic:** edit `process_file` in `lambda/handler.py`
  — it's isolated from the CDK infrastructure code, so changing the parsing
  logic never requires touching `takehome_stack.py`.
- **Changing the bucket policy:** the `DenyInsecureTransport` statement in
  `takehome_stack.py` is the only bucket policy statement; add further
  statements the same way, via `bucket.add_to_resource_policy`.
- **Adding a real deploy pipeline:** the CI workflow deliberately stops at
  `cdk synth` — no AWS credentials are stored anywhere in this repo. A real
  deploy job would authenticate via GitHub Actions' OIDC federation
  straight to an AWS IAM role scoped to this stack, the same pattern used
  in production CI/CD, rather than long-lived access keys.
