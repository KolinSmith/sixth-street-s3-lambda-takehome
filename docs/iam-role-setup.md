# IAM setup for the GitHub Actions deploy role

`deploy.yml` authenticates via OIDC to an IAM role,
**`sixth-street-takehome-github-actions-deploy`**. This documents exactly
what that role trusts, exactly what it's allowed to do, and how to
recreate it — because **it doesn't currently exist**.

## Current status: torn down

After the take-home work was live-tested, every AWS resource this project
created was deliberately deleted (`cdk destroy`, the `CDKToolkit` bootstrap
stack, the CDK asset bucket, this role, its policy, and the GitHub OIDC
identity provider) to stop incurring any AWS cost while idle. `deploy.yml`
still references this role's ARN — running the workflow today will fail
at the "Configure AWS credentials via OIDC" step until the role is
recreated using the steps below.

## The OIDC identity provider

One per AWS account, shared by any repo using GitHub Actions OIDC in this
account — not specific to this project, but this project's role depends
on it existing.

```
Provider URL: https://token.actions.githubusercontent.com
Client ID (audience): sts.amazonaws.com
Thumbprint: 1c58a3a8518e8759bf075b76b750d4f2df264fcd
```

(AWS validates the certificate chain itself for well-known providers like
this one — the thumbprint value is required by the API but isn't the real
trust boundary; the trust policy's `sub` condition below is.)

## The role's trust policy

Controls **who can assume the role** — i.e., who can trigger a deploy.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::249091361100:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:KolinSmith@15791306/sixth-street-s3-lambda-takehome@1376523496:*"
        }
      }
    }
  ]
}
```

**Why the `sub` condition looks like that:** GitHub's OIDC token embeds
immutable owner/repo IDs alongside the names
(`repo:OWNER@OWNER_ID/REPO@REPO_ID:ref:...`), not just
`repo:OWNER/REPO:...` — this was a real bug hit during setup (see the
git history for `fix: correct OIDC trust policy to match GitHub's sub
claim format`). Matching on the IDs rather than just the names also means
the trust survives a future rename of the repo or your GitHub username.

## The role's permissions policy

Controls **what the role can do**, once assumed. Deliberately scoped to
only this project's own resources — not `AdministratorAccess`, not a
broad CDK-deploy policy reused across projects.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormationStacks",
      "Effect": "Allow",
      "Action": "cloudformation:*",
      "Resource": [
        "arn:aws:cloudformation:*:249091361100:stack/CDKToolkit/*",
        "arn:aws:cloudformation:*:249091361100:stack/SixthStreetTakehomeStack/*"
      ]
    },
    {
      "Sid": "CdkBootstrapAssets",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::cdk-hnb659fds-assets-249091361100-*",
        "arn:aws:s3:::cdk-hnb659fds-assets-249091361100-*/*"
      ]
    },
    {
      "Sid": "TakehomeBucketTestAccess",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::sixthstreettakehomestack-*",
        "arn:aws:s3:::sixthstreettakehomestack-*/*"
      ]
    },
    {
      "Sid": "TakehomeLambdaLogs",
      "Effect": "Allow",
      "Action": ["logs:DescribeLogStreams", "logs:GetLogEvents", "logs:FilterLogEvents"],
      "Resource": "arn:aws:logs:*:249091361100:log-group:/aws/lambda/SixthStreetTakehomeStack-*:*"
    },
    {
      "Sid": "CdkBootstrapEcr",
      "Effect": "Allow",
      "Action": "ecr:*",
      "Resource": "arn:aws:ecr:*:249091361100:repository/cdk-hnb659fds-container-assets-249091361100-*"
    },
    {
      "Sid": "CdkBootstrapEcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "CdkBootstrapSsm",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:PutParameter", "ssm:DeleteParameter"],
      "Resource": "arn:aws:ssm:*:249091361100:parameter/cdk-bootstrap/hnb659fds/*"
    },
    {
      "Sid": "CdkBootstrapAndStackRoles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole",
        "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
        "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
        "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy",
        "iam:CreatePolicyVersion", "iam:DeletePolicyVersion", "iam:ListPolicyVersions",
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::249091361100:role/cdk-hnb659fds-*",
        "arn:aws:iam::249091361100:policy/cdk-hnb659fds-*",
        "arn:aws:iam::249091361100:role/SixthStreetTakehomeStack-*"
      ]
    },
    {
      "Sid": "AssumeBootstrapRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::249091361100:role/cdk-hnb659fds-*"
    }
  ]
}
```

### What each statement is for

| Statement | Why it's needed |
|---|---|
| `CloudFormationStacks` | `cdk bootstrap` and `cdk deploy` both work by creating/updating a CloudFormation stack (`CDKToolkit` for bootstrap, `SixthStreetTakehomeStack` for the app). Scoped to only these two stacks by name — can't touch any other stack in the account. |
| `CdkBootstrapAssets` | CDK uploads the synthesized template and Lambda code as assets to a staging S3 bucket it creates during bootstrap. Scoped to that bucket's name pattern only. |
| `TakehomeBucketTestAccess` | Not needed for deploy itself — added so live end-to-end tests (uploading a real file, checking the Lambda's behavior) could be run against the deployed bucket during development. |
| `TakehomeLambdaLogs` | Read-only CloudWatch Logs access, scoped to only this Lambda's log group — used to verify the Lambda actually parsed test files correctly. |
| `CdkBootstrapEcr` / `CdkBootstrapEcrAuth` | CDK bootstrap always provisions an ECR repo for container image assets, even though this stack has none. `GetAuthorizationToken` is account-wide by necessity (ECR has no per-repo scoping for that specific action), everything else is scoped to the one bootstrap repo. |
| `CdkBootstrapSsm` | CDK bootstrap records its own version in an SSM parameter (`/cdk-bootstrap/hnb659fds/version`) and CDK checks it on every deploy. |
| `CdkBootstrapAndStackRoles` | CDK bootstrap creates ~5 IAM roles for itself (deploy role, file-publishing role, lookup role, etc.), and the app stack creates its own Lambda execution role. This is the broadest statement, but still resource-scoped to only `cdk-hnb659fds-*` named resources and this specific stack's role naming pattern — can't create, modify, or delete any *other* IAM role or policy in the account. |
| `AssumeBootstrapRoles` | The actual `cdk deploy` flow works by this role assuming CDK's own bootstrap-created roles (e.g. the `cfn-exec-role`), which is where the real resource-creation permissions for the S3 bucket/Lambda/bucket-policy live — this role itself never directly creates those. |

**Deliberately not scoped further:** the `cfn-exec-role` that CloudFormation
actually assumes to build the S3 bucket/Lambda/policy keeps CDK's default
`AdministratorAccess` (not customized). Hand-scoping that role to the exact
actions a real deploy needs is fragile — CDK's own S3-notification and
auto-delete-objects custom resources make calls that are easy to
under-scope and break mid-deploy. The safety boundary here is on **who can
trigger a deploy and to which two stacks**, not on limiting what
CloudFormation itself can build once triggered.

## Recreating the role

Using an account with sufficient IAM permissions (this was originally done
with root, one-time, specifically because creating an OIDC provider and
IAM entities isn't something the scoped deploy role can do for itself):

```bash
# 1. Create the OIDC provider (skip if one already exists for this account)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 1c58a3a8518e8759bf075b76b750d4f2df264fcd

# 2. Create the permissions policy (save the JSON above as policy.json)
aws iam create-policy \
  --policy-name sixth-street-takehome-cdk-deploy \
  --policy-document file://policy.json

# 3. Create the role with the trust policy above (save as trust-policy.json)
aws iam create-role \
  --role-name sixth-street-takehome-github-actions-deploy \
  --assume-role-policy-document file://trust-policy.json

# 4. Attach the policy to the role
aws iam attach-role-policy \
  --role-name sixth-street-takehome-github-actions-deploy \
  --policy-arn arn:aws:iam::249091361100:policy/sixth-street-takehome-cdk-deploy
```

After this, `deploy.yml` will work again as-is — the role ARN it
references doesn't change on recreation as long as the same role name is
used.
