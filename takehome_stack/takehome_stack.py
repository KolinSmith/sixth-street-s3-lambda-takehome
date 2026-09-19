from aws_cdk import Stack
from constructs import Construct


class TakehomeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Resources added in later tasks: S3 bucket + policy (Task 2),
        # Lambda + event notification (Task 3).
