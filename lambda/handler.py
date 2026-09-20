import logging

import boto3

# Lambda's default logging setup ships logger.info()/.error() calls straight to CloudWatch
# Logs automatically — nothing extra needed to "connect" this to CloudWatch.
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # without this, only warning/error would show up — info wouldn't

# boto3 is AWS's Python SDK — this is how any Python code (Lambda included) talks to AWS
# services. Created once at module load time (outside any function) so Lambda can reuse this
# same client across multiple invocations of a "warm" container, instead of reconnecting
# every single time.
s3_client = boto3.client("s3")


# This is the function CDK pointed at via handler="handler.lambda_handler" — it's the actual
# entry point AWS Lambda calls. "event" is what triggered it (here, an S3 notification);
# "context" carries runtime info (request id, time remaining, etc.) — unused here, but every
# Lambda handler must accept it as a parameter.
def lambda_handler(event, context):
    # An S3 event notification can bundle multiple file uploads into one invocation, listed
    # under event["Records"]. .get("Records", []) means "give me the Records list, or an
    # empty list if it's missing" — safer than event["Records"], which would crash if the key
    # didn't exist.
    for record in event.get("Records", []):
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]  # the uploaded file's path/name inside the bucket
        process_file(bucket_name, object_key)


# The type hints (bucket_name: str, object_key: str, -> None) are documentation, not
# enforcement — Python won't stop you from passing the wrong type, but they tell a reader
# (and tools like your editor) exactly what's expected in and out.
def process_file(bucket_name: str, object_key: str) -> None:
    """Read a single-line file from S3 and log its comma-separated fields.

    The uploaded file's format isn't specified by the assignment — this
    assumes comma-separated values, the most common plain-text convention,
    and logs that assumption's result rather than guessing further.
    """
    try:
        # Download the file's contents. get_object() doesn't give you the raw text directly —
        # response["Body"] is a stream, so .read() pulls all the bytes out of it.
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        # .decode("utf-8") turns those raw bytes into an actual Python string; .strip()
        # trims any trailing newline/whitespace the file might have.
        content = response["Body"].read().decode("utf-8").strip()
    except Exception as exc:
        # Covers a missing file, no permissions, garbled encoding, etc. Logging and
        # returning (instead of letting the exception propagate) matters here: an S3-
        # triggered Lambda that throws gets automatically retried by AWS with the exact same
        # bad input, so "fail loud but don't raise" avoids an infinite retry loop.
        logger.error(
            "Failed to read s3://%s/%s: %s", bucket_name, object_key, exc
        )
        return

    if not content:
        logger.error(
            "File s3://%s/%s is empty, nothing to parse", bucket_name, object_key
        )
        return

    # A list comprehension: for every piece produced by content.split(","), strip its
    # whitespace, and collect the results into a new list called `fields`. Equivalent to:
    #   fields = []
    #   for field in content.split(","):
    #       fields.append(field.strip())
    fields = [field.strip() for field in content.split(",")]

    # %s/%d are old-style string placeholders — logger.info fills them in from the
    # arguments that follow, in order. (Using these instead of an f-string here is a minor
    # logging best practice: the string only actually gets built if this log level is
    # enabled, instead of always being built up front.)
    logger.info(
        "Parsed %d field(s) from s3://%s/%s: %s",
        len(fields),
        bucket_name,
        object_key,
        fields,
    )
