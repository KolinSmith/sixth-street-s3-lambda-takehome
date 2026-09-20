from aws_cdk import Stack, RemovalPolicy, Duration
# CDK groups AWS services into modules named "aws_<service>". We rename each on import
# (e.g. "as s3") purely so the code below can write s3.Bucket instead of aws_s3.Bucket.
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_lambda as _lambda  # "lambda" is a reserved Python keyword, hence the underscore
from aws_cdk import aws_iam as iam
from constructs import Construct


# A CDK "Stack" is a Python class that maps 1:1 to one CloudFormation stack (one deployable
# unit in AWS). Inheriting from aws_cdk.Stack is what gives this class all of CDK's
# deploy/synth machinery for free — we only need to define what goes inside it.
class TakehomeStack(Stack):
    # __init__ runs once, when this stack is instantiated in app.py. "scope" is the parent
    # (the cdk.App() from app.py), "construct_id" is this stack's name ("SixthStreetTakehomeStack").
    # **kwargs collects any extra optional arguments (like env/region) so they pass through
    # to CDK's own Stack.__init__ without us having to name them all individually.
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        # Required first line in any subclass __init__: runs the parent Stack class's own
        # setup before we add anything of our own.
        super().__init__(scope, construct_id, **kwargs)

        # --- The S3 bucket (assignment requirement: "An S3 bucket") -----------------------
        # self.bucket makes this an attribute of the class (accessible as `self.bucket`
        # anywhere else in this method, and from outside via TakehomeStack().bucket).
        self.bucket = s3.Bucket(
            self,                                       # parent construct = this stack
            "TakehomeBucket",                            # logical id CDK uses internally (not the real AWS bucket name — AWS generates that)
            encryption=s3.BucketEncryption.S3_MANAGED,    # encrypt objects at rest, AWS manages the key
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # nothing in this bucket can ever be made public
            removal_policy=RemovalPolicy.DESTROY,         # `cdk destroy` actually deletes this bucket (default would leave it behind)
            auto_delete_objects=True,                     # ...and empties it first, since S3 normally refuses to delete a non-empty bucket
        )

        # --- The bucket policy (assignment requirement: "A bucket policy") ----------------
        # add_to_resource_policy attaches an IAM policy statement directly to the bucket
        # itself (as opposed to a policy attached to a user/role) — this is what makes it a
        # *bucket* policy specifically.
        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyInsecureTransport",       # just a human-readable label for this statement
                effect=iam.Effect.DENY,             # this statement blocks matching requests
                principals=[iam.AnyPrincipal()],    # applies to literally anyone/anything, no exceptions
                actions=["s3:*"],                   # every S3 action (read, write, list, delete...)
                resources=[self.bucket.bucket_arn, f"{self.bucket.bucket_arn}/*"],  # the bucket itself AND every object inside it
                conditions={"Bool": {"aws:SecureTransport": "false"}},  # ...but ONLY when the request isn't using HTTPS
            )
        )
        # Net effect: any request to this bucket over plain HTTP gets denied. HTTPS requests
        # are unaffected — this statement never matches them, so they fall through to normal
        # bucket permissions.

        # --- The Lambda (assignment requirement: "A Lambda that processes S3 events") -----
        self.processor_function = _lambda.Function(
            self,
            "FileProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",   # "<filename-without-.py>.<function-name>" inside the code below — points at lambda/handler.py's lambda_handler()
            code=_lambda.Code.from_asset("lambda"),  # zip up everything in the lambda/ folder and upload it as this function's code
            timeout=Duration.seconds(30),        # kill the function if it hasn't finished in 30s (files here are tiny, this is generous)
        )

        # grant_read() is a CDK convenience method: it writes the IAM policy statements that
        # let processor_function call GetObject/GetBucket*/List* — but ONLY on self.bucket,
        # nothing else in the account. Doing this by hand would mean writing that IAM policy
        # statement out explicitly, the same way we did above for the bucket policy.
        self.bucket.grant_read(self.processor_function)

        # This is the actual trigger: "whenever an object is created in self.bucket, invoke
        # processor_function." OBJECT_CREATED covers PutObject, CopyObject, and multipart
        # upload completion — any way a new file can land in the bucket.
        self.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.processor_function),
        )
        # Under the hood, add_event_notification() and auto_delete_objects=True above each
        # generate a small extra "custom resource" Lambda of their own (visible in `cdk diff`
        # as BucketNotificationsHandler... and CustomS3AutoDeleteObjects...) — CDK's own
        # plumbing to make these two features work, not something we wrote ourselves.
