import os

from dotenv import load_dotenv


def get_s3_config():
    # Reload .env values so updates are picked up without code changes.
    load_dotenv(override=True)
    return {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_REGION"),
        "bucket": os.getenv("AWS_S3_BUCKET_NAME"),
    }
