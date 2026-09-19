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
