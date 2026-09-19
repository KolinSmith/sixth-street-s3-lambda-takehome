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
