# core/s3_client.py

import os
import boto3
from typing import Tuple


def get_s3() -> Tuple[boto3.client, str, str]:
    """
    Get S3 client, bucket name, and region.
    Returns: (s3_client, bucket_name, region)
    Raises RuntimeError if AWS credentials are missing.
    """
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket = os.getenv("AWS_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-2")

    if not all([key, secret, bucket]):
        raise RuntimeError("Missing AWS credentials")

    client = boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name=region,
    )

    return client, bucket, region

