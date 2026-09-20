import aws_cdk as core
from aws_cdk.assertions import Template, Match

from takehome_stack.takehome_stack import TakehomeStack

# pytest auto-discovers any function whose name starts with "test_" in this file — no
# registration or decorator needed, just the naming convention.


# A small helper, reused by every test below, so each test isn't repeating this setup.
# Functions starting with "_" are a Python convention meaning "internal to this file, not
# meant to be imported/used elsewhere" — pytest itself ignores it since it doesn't start
# with "test_".
def _synth_template() -> Template:
    app = core.App()
    stack = TakehomeStack(app, "TestStack")
    # Template.from_stack() runs the same synth process `cdk synth` does, but in memory —
    # no AWS account, no network call, just Python turning our stack into the CloudFormation
    # JSON it would produce. Template gives us methods to inspect that JSON.
    return Template.from_stack(stack)


def test_bucket_created():
    template = _synth_template()
    # Asserts the synthesized template contains exactly 1 resource of this CloudFormation
    # type. Fails loudly (with a diff) if the count is 0 or more than 1.
    template.resource_count_is("AWS::S3::Bucket", 1)


def test_bucket_blocks_public_access():
    template = _synth_template()
    # has_resource_properties: find a resource of this type, assert it has (at least) these
    # properties set. This mirrors the block_public_access=BLOCK_ALL line in
    # takehome_stack.py — proving that flag actually produces the CloudFormation properties
    # we expect, not just that we wrote the line.
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
    # Match.object_like / Match.array_with mean "this must be present, but other keys/items
    # can exist too" — a looser match than an exact equality check, so this test doesn't
    # break if CDK's generated policy ever gains extra fields we don't care about.
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


def test_lambda_function_created():
    template = _synth_template()
    # Confirms the Lambda exists with the exact handler string and runtime we set in
    # takehome_stack.py — catches a typo like "handlers.lambda_handler" that would otherwise
    # only surface as a runtime error after a real deploy.
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.14",
        },
    )


def test_lambda_has_s3_event_notification():
    template = _synth_template()
    # S3 event notifications are wired via a custom resource that calls
    # PutBucketNotificationConfiguration — assert the custom resource exists
    # rather than inspecting bucket properties directly, since that's how
    # CDK's add_event_notification is actually implemented under the hood.
    template.resource_count_is("Custom::S3BucketNotifications", 1)
