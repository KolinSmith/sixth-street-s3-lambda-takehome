# S3 + Lambda CDK Take-Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, tested AWS CDK (Python) app that provisions an S3 bucket, a bucket policy, and a Lambda that parses single-line files on upload — deployable and defensible, without requiring a live AWS deploy to prove correctness.

**Architecture:** One CDK stack (`TakehomeStack`) defines an S3 bucket with a deny-non-HTTPS bucket policy, and a Python Lambda wired to the bucket's `OBJECT_CREATED` event via S3's native event notification (no queue/topic in between). The Lambda reads the uploaded object, splits its single line on commas, and logs the parsed fields — malformed or empty files are logged as errors and handled gracefully, not thrown.

**Tech Stack:** AWS CDK v2 (`aws-cdk-lib`, Python), `constructs`, `boto3` (Lambda runtime + local dev), `pytest` + `aws_cdk.assertions` (CDK unit tests), `unittest.mock` (Lambda unit tests), GitHub Actions (CI).

**Spec:** `docs/superpowers/specs/2026-09-18-sixth-street-cdk-takehome-design.md`

## Global Constraints

- Python: latest supported by CDK — target **3.12** (matches the assignment's "latest supported version of Python").
- No live AWS deploy or live AWS credentials anywhere in this repo or its CI — every test must pass without an AWS account. (Decided in brainstorming session, 2026-09-18.)
- No Terraform Cloud, no queue/topic infrastructure between S3 and the Lambda, no DynamoDB or other data store — CDK is the sole deployment mechanism (spec, "Out of scope" section).
- Bucket policy: single explicit `Deny` statement on non-HTTPS requests (`aws:SecureTransport: false`), written explicitly via `iam.PolicyStatement`, not the `enforce_ssl` shortcut flag — this take-home is evaluated on demonstrated understanding, and explicit code reads clearer than a boolean flag in a live defense.
- Lambda parses its single line as **comma-separated values** — a documented assumption, since the spec defines no format. State this assumption in code comments and the README, not just in this plan.
- IAM: the Lambda's execution role gets exactly `s3:GetObject` scoped to this one bucket (via `bucket.grant_read`), nothing broader.

---

### Task 1: Project scaffolding + empty stack that synthesizes

**Files:**
- Create: `requirements.txt`
- Create: `cdk.json`
- Create: `.gitignore`
- Create: `app.py`
- Create: `takehome_stack/__init__.py`
- Create: `takehome_stack/takehome_stack.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`

**Interfaces:**
- Produces: `TakehomeStack` class in `takehome_stack/takehome_stack.py`, constructor signature `TakehomeStack(scope: Construct, construct_id: str, **kwargs)` — every later task adds resources inside this class.

- [x] **Step 1: Write `requirements.txt`**

```
aws-cdk-lib>=2.150.0
constructs>=10.0.0
pytest>=8.0.0
boto3>=1.34.0
```

- [x] **Step 2: Write `cdk.json`**

```json
{
  "app": "python3 app.py",
  "watch": {
    "include": ["**"],
    "exclude": [
      "README.md",
      "cdk*.json",
      "requirements*.txt",
      "**/__init__.py",
      "python/__pycache__",
      "tests"
    ]
  },
  "context": {}
}
```

- [x] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
cdk.out/
.venv/
venv/
.pytest_cache/
*.egg-info/
```

- [x] **Step 4: Create empty package files**

```bash
touch takehome_stack/__init__.py tests/__init__.py tests/unit/__init__.py
```

- [x] **Step 5: Write the minimal (empty) stack**

`takehome_stack/takehome_stack.py`:
```python
from aws_cdk import Stack
from constructs import Construct


class TakehomeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Resources added in later tasks: S3 bucket + policy (Task 2),
        # Lambda + event notification (Task 3).
```

- [x] **Step 6: Write `app.py`**

```python
#!/usr/bin/env python3
import aws_cdk as cdk

from takehome_stack.takehome_stack import TakehomeStack

app = cdk.App()
TakehomeStack(app, "SixthStreetTakehomeStack")

app.synth()
```

- [x] **Step 7: Install dependencies and verify synth works**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk synth
```
Expected: prints a valid (near-empty) CloudFormation template to stdout, exits 0. No AWS credentials needed — this stack has no account/region-specific lookups.

- [x] **Step 8: Commit**

```bash
git add requirements.txt cdk.json .gitignore app.py takehome_stack/ tests/
git commit -m "chore: scaffold CDK app with empty stack that synthesizes"
```

---

### Task 2: S3 bucket + deny-non-HTTPS bucket policy

**Files:**
- Modify: `takehome_stack/takehome_stack.py`
- Create: `tests/unit/test_takehome_stack.py`

**Interfaces:**
- Consumes: `TakehomeStack` from Task 1.
- Produces: `self.bucket` (an `s3.Bucket` instance) as an attribute on `TakehomeStack` — Task 3's Lambda wiring reads `self.bucket`.

- [x] **Step 1: Write the failing test**

`tests/unit/test_takehome_stack.py`:
```python
import aws_cdk as core
from aws_cdk.assertions import Template, Match

from takehome_stack.takehome_stack import TakehomeStack


def _synth_template() -> Template:
    app = core.App()
    stack = TakehomeStack(app, "TestStack")
    return Template.from_stack(stack)


def test_bucket_created():
    template = _synth_template()
    template.resource_count_is("AWS::S3::Bucket", 1)


def test_bucket_blocks_public_access():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_bucket_policy_denies_insecure_transport():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {
                                        "Bool": {"aws:SecureTransport": "false"}
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_takehome_stack.py -v`
Expected: all 3 FAIL — `AttributeError` or resource-count assertion failures, since no bucket exists yet.

- [x] **Step 3: Implement the bucket + policy**

`takehome_stack/takehome_stack.py`:
```python
from aws_cdk import Stack, RemovalPolicy
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_iam as iam
from constructs import Construct


class TakehomeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "TakehomeBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deny any request that isn't using TLS. Explicit statement (rather
        # than the `enforce_ssl` shortcut) so the policy's intent is visible
        # directly in the stack code.
        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyInsecureTransport",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[self.bucket.bucket_arn, f"{self.bucket.bucket_arn}/*"],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        # Resources added in Task 3: Lambda + event notification.
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_takehome_stack.py -v`
Expected: all 3 PASS.

- [x] **Step 5: Commit**

```bash
git add takehome_stack/takehome_stack.py tests/unit/test_takehome_stack.py
git commit -m "feat: add S3 bucket with deny-non-HTTPS bucket policy"
```

---

### Task 3: Lambda function + S3 event notification wiring

**Files:**
- Create: `lambda/handler.py` (stub only — real parsing logic in Task 4)
- Modify: `takehome_stack/takehome_stack.py`
- Modify: `tests/unit/test_takehome_stack.py`

**Interfaces:**
- Consumes: `self.bucket` from Task 2.
- Produces: `self.processor_function` (an `aws_lambda.Function` instance) on `TakehomeStack`. The Lambda's handler entry point is `handler.lambda_handler` — Task 4 fills in `lambda_handler`'s real body; this task only needs it to exist so CDK can package the asset.

- [x] **Step 1: Write the Lambda stub**

`lambda/handler.py`:
```python
def lambda_handler(event, context):
    # Real parsing logic added in Task 4.
    pass
```

- [x] **Step 2: Write the failing test**

Append to `tests/unit/test_takehome_stack.py`:
```python
def test_lambda_function_created():
    template = _synth_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.12",
        },
    )


def test_lambda_has_s3_event_notification():
    template = _synth_template()
    # S3 event notifications are wired via a custom resource that calls
    # PutBucketNotificationConfiguration — assert the custom resource exists
    # rather than inspecting bucket properties directly, since that's how
    # CDK's add_event_notification is actually implemented under the hood.
    template.resource_count_is("Custom::S3BucketNotifications", 1)
```

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_takehome_stack.py -v`
Expected: the two new tests FAIL (no Lambda or notification exists yet); the three from Task 2 still PASS.

- [x] **Step 4: Implement the Lambda + event wiring**

`takehome_stack/takehome_stack.py`:
```python
from aws_cdk import Stack, RemovalPolicy, Duration
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
from constructs import Construct


class TakehomeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "TakehomeBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyInsecureTransport",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[self.bucket.bucket_arn, f"{self.bucket.bucket_arn}/*"],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        self.processor_function = _lambda.Function(
            self,
            "FileProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
        )

        self.bucket.grant_read(self.processor_function)

        self.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.processor_function),
        )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_takehome_stack.py -v`
Expected: all 5 tests PASS.

- [x] **Step 6: Commit**

```bash
git add lambda/handler.py takehome_stack/takehome_stack.py tests/unit/test_takehome_stack.py
git commit -m "feat: wire Lambda to S3 ObjectCreated events"
```

---

### Task 4: Lambda parsing logic + unit tests

**Files:**
- Modify: `lambda/handler.py`
- Create: `tests/unit/test_handler.py`

**Interfaces:**
- Consumes: nothing from other tasks (the Lambda handler is self-contained; it only depends on `boto3`, which is available in the Lambda runtime and is a listed dependency for local testing).
- Produces: `process_file(bucket_name: str, object_key: str) -> None` and `lambda_handler(event, context) -> None` in `lambda/handler.py`. These exact names are the module's public interface — nothing else in the repo calls into this module directly (CDK references it by file path, not by Python import).

**Note on imports:** `lambda` is a Python reserved keyword, so a test file cannot do `from lambda import handler`— that's a `SyntaxError`. The test instead adds the `lambda/` directory to `sys.path` and imports the module as a bare top-level `handler`, which sidesteps the keyword entirely.

- [x] **Step 1: Write the failing tests**

`tests/unit/test_handler.py`:
```python
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda"))
import handler  # noqa: E402  (path must be set before this import)


def _mock_s3_object(body_bytes: bytes):
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    return {"Body": mock_body}


def test_process_file_parses_comma_separated_line(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(
            b"alice,32,dallas"
        )
        with caplog.at_level("INFO"):
            handler.process_file("test-bucket", "test-key.txt")

    mock_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="test-key.txt"
    )
    assert "alice" in caplog.text
    assert "32" in caplog.text
    assert "dallas" in caplog.text


def test_process_file_handles_empty_file(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(b"")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "empty-key.txt")

    assert "empty" in caplog.text.lower()


def test_process_file_handles_get_object_failure(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.side_effect = Exception("boom")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "missing-key.txt")

    assert "failed" in caplog.text.lower()


def test_lambda_handler_processes_each_record():
    event = {
        "Records": [
            {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1.txt"}}},
            {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2.txt"}}},
        ]
    }
    with patch.object(handler, "process_file") as mock_process:
        handler.lambda_handler(event, context=None)

    assert mock_process.call_count == 2
    mock_process.assert_any_call("b1", "k1.txt")
    mock_process.assert_any_call("b2", "k2.txt")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_handler.py -v`
Expected: all 4 FAIL — `handler.s3_client` doesn't exist yet, `process_file` doesn't exist yet.

- [x] **Step 3: Implement the real handler**

`lambda/handler.py`:
```python
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]
        process_file(bucket_name, object_key)


def process_file(bucket_name: str, object_key: str) -> None:
    """Read a single-line file from S3 and log its comma-separated fields.

    The uploaded file's format isn't specified by the assignment — this
    assumes comma-separated values, the most common plain-text convention,
    and logs that assumption's result rather than guessing further.
    """
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content = response["Body"].read().decode("utf-8").strip()
    except Exception as exc:
        logger.error(
            "Failed to read s3://%s/%s: %s", bucket_name, object_key, exc
        )
        return

    if not content:
        logger.error(
            "File s3://%s/%s is empty, nothing to parse", bucket_name, object_key
        )
        return

    fields = [field.strip() for field in content.split(",")]
    logger.info(
        "Parsed %d field(s) from s3://%s/%s: %s",
        len(fields),
        bucket_name,
        object_key,
        fields,
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_handler.py -v`
Expected: all 4 PASS.

- [x] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all 9 tests PASS (5 from `test_takehome_stack.py`, 4 from `test_handler.py`).

- [x] **Step 6: Commit**

```bash
git add lambda/handler.py tests/unit/test_handler.py
git commit -m "feat: implement Lambda file-parsing logic with error handling"
```

---

### Task 5: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), the full test suite (Tasks 2-4), `cdk synth` (works since Task 1, no AWS credentials required).
- Produces: nothing consumed by other tasks — this is a leaf task.

- [x] **Step 1: Write the workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: ["master"]

jobs:
  synth-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set up Node (for the CDK CLI)
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install CDK CLI
        run: npm install -g aws-cdk

      - name: Install Python dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests
        run: pytest tests/ -v

      - name: CDK synth
        run: cdk synth
        # No AWS credentials configured on purpose — this stack has no
        # account/region-specific lookups, so synth succeeds without them.
        # A real deploy job, if added later, would authenticate via GitHub
        # OIDC straight to an AWS IAM role rather than stored access keys.
```

- [x] **Step 2: Verify the workflow is valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no output, exits 0 (confirms valid YAML syntax before it's ever pushed).

- [x] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for tests and cdk synth"
```

---

### Task 6: README with deploy instructions + Excalidraw diagram

**Files:**
- Create: `README.md`
- Create: `docs/images/architecture.png` (produced by Kolin via Excalidraw.com, see Step 1 — not something an agent can generate directly)

**Interfaces:**
- Consumes: the finished stack (Tasks 1-3) and Lambda (Task 4) to describe accurately.
- Produces: nothing — this is the final task.

- [ ] **Step 1: Kolin draws the diagram on Excalidraw.com**

This step is manual — Excalidraw.com is a GUI the assignment explicitly asks for by name, so this isn't something to script around. Draw exactly this, matching the architecture already agreed in the spec:

1. Go to https://excalidraw.com
2. Draw 3 rectangles, labeled: **"S3 Bucket"**, **"Lambda (Python)"**, **"CloudWatch Logs"**.
3. Draw a 4th, smaller rectangle near the S3 Bucket labeled **"Bucket Policy: Deny non-HTTPS (aws:SecureTransport)"**, connected to the S3 Bucket box with a dotted line (Excalidraw supports dashed/dotted line styles in the left panel).
4. Arrow from **S3 Bucket → Lambda**, labeled **"ObjectCreated event"**.
5. Arrow from **Lambda → S3 Bucket**, labeled **"GetObject"** (a second arrow, opposite direction — the Lambda reads the file back).
6. Arrow from **Lambda → CloudWatch Logs**, labeled **"log parsed fields"**.
7. Export: menu (top-left) → **Export image** → **PNG** → save as `architecture.png`.
8. Save the file into this repo:
   ```bash
   mkdir -p docs/images
   mv ~/Downloads/architecture.png docs/images/architecture.png
   ```

- [x] **Step 2: Write the README**

`README.md`:
````markdown
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
````

- [ ] **Step 3: Verify the README renders sensibly**

Run: `cat README.md` and visually confirm the image reference path (`docs/images/architecture.png`) matches where the file actually is: `ls docs/images/architecture.png`
Expected: file exists, path in the README matches exactly.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/images/architecture.png
git commit -m "docs: add README with architecture diagram and deploy instructions"
```

- [ ] **Step 5: Push the branch and confirm the GitHub mirror synced**

```bash
git push
```

Then check: `gh api repos/KolinSmith/sixth-street-s3-lambda-takehome/commits --jq '.[0].commit.message'`
Expected: shows the most recent commit message, confirming the Forgejo push-mirror synced this branch's commits to GitHub (mirror is configured with `sync_on_commit: true`, see the earlier setup this session).

---

## Self-Review Notes (completed during plan authoring)

**Spec coverage:** every numbered item in the assignment maps to a task — CDK code (Tasks 1-3), Lambda parsing (Task 4), architecture diagram + README (Task 6), optional deployment workflow (Task 5). The spec's explicit design decisions (no live deploy, no Terraform Cloud, comma-separated assumption, deny-non-HTTPS policy, S3 direct-to-Lambda notification, CloudWatch-only "processing") are all implemented exactly as documented, not reinterpreted.

**Placeholder scan:** no TBD/TODO; the one manual step (Task 6, Step 1) is manual because the assignment names a specific GUI tool by URL, not because anything was left undecided — the exact shapes, labels, and arrows to draw are fully specified.

**Type consistency:** `self.bucket` (Task 2) is read by Task 3's `bucket.grant_read` / `add_event_notification` calls. `self.processor_function` (Task 3) is not consumed by any later task directly (Task 4 only touches `lambda/handler.py`, which CDK references by file path, not by CDK object reference) — consistent throughout. `process_file(bucket_name: str, object_key: str) -> None` and `lambda_handler(event, context) -> None` (Task 4) match their usage in Task 3's stub and in the Task 4 tests.
