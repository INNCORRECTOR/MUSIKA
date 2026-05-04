import os
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class UploadValidationError(Exception):
    pass


class UploadServiceError(Exception):
    pass


def build_public_s3_url(bucket: str, region: str, object_key: str) -> str:
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"


def upload_image_and_get_url(file, s3_config):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise UploadValidationError("Only image files are allowed.")

    if (
        not s3_config["access_key"]
        or not s3_config["secret_key"]
        or not s3_config["region"]
        or not s3_config["bucket"]
    ):
        raise UploadValidationError("Missing AWS configuration in .env")

    s3_client = boto3.client(
        "s3",
        region_name=s3_config["region"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
    )

    file_ext = os.path.splitext(file.filename or "")[1]
    object_key = f"uploads/{uuid4().hex}{file_ext}"

    try:
        s3_client.upload_fileobj(
            file.file,
            s3_config["bucket"],
            object_key,
            ExtraArgs={"ContentType": file.content_type},
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        msg = error.get("Message", "Unknown AWS error")
        raise UploadServiceError(f"AWS error [{code}]: {msg}") from exc
    except BotoCoreError as exc:
        raise UploadServiceError("Upload failed due to AWS SDK/network issue.") from exc

    image_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": s3_config["bucket"], "Key": object_key},
        ExpiresIn=3600,
    )
    public_image_url = build_public_s3_url(s3_config["bucket"], s3_config["region"], object_key)
    return object_key, image_url, public_image_url


def delete_image_by_key(object_key: str, s3_config) -> None:
    if (
        not s3_config["access_key"]
        or not s3_config["secret_key"]
        or not s3_config["region"]
        or not s3_config["bucket"]
    ):
        raise UploadValidationError("Missing AWS configuration in .env")

    s3_client = boto3.client(
        "s3",
        region_name=s3_config["region"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
    )

    try:
        s3_client.delete_object(Bucket=s3_config["bucket"], Key=object_key)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        msg = error.get("Message", "Unknown AWS error")
        raise UploadServiceError(f"AWS error [{code}]: {msg}") from exc
    except BotoCoreError as exc:
        raise UploadServiceError("Delete failed due to AWS SDK/network issue.") from exc
