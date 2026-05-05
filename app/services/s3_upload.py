import io
import os
import re
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError

WEBP_QUALITY = int(os.getenv("UPLOAD_WEBP_QUALITY", "85"))
WEBP_CONTENT_TYPE = "image/webp"


class UploadValidationError(Exception):
    pass


class UploadServiceError(Exception):
    pass


def build_public_s3_url(bucket: str, region: str, object_key: str) -> str:
    return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"


def _prepare_image_for_webp(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA"):
        return im
    if im.mode == "P":
        if "transparency" in im.info:
            return im.convert("RGBA")
        return im.convert("RGB")
    if im.mode == "RGB":
        return im
    return im.convert("RGB")


def _is_svg_upload(content_type: str | None, filename: str | None, raw: bytes) -> bool:
    ct = (content_type or "").lower()
    if "svg" in ct:
        return True
    if (filename or "").lower().endswith(".svg"):
        return True
    head = raw.lstrip()[:2048].lower()
    if head.startswith((b"<svg", b"<?xml", b"<!doctype svg")):
        return bool(re.search(rb"<svg[\s/>]", head))
    return False


def _raster_bytes_to_webp(raw: bytes, quality: int) -> bytes:
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        if getattr(im, "is_animated", False):
            im.seek(0)
        prepared = _prepare_image_for_webp(im)
        out = io.BytesIO()
        prepared.save(out, "WEBP", quality=quality, method=6)
        return out.getvalue()


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

    raw = file.file.read()
    try:
        file.file.seek(0)
    except OSError:
        pass

    if not raw:
        raise UploadValidationError("Empty file.")

    s3_client = boto3.client(
        "s3",
        region_name=s3_config["region"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
    )

    filename = file.filename or ""
    content_type = file.content_type

    if _is_svg_upload(content_type, filename, raw):
        file_ext = ".svg"
        upload_body = io.BytesIO(raw)
        upload_content_type = content_type if "svg" in (content_type or "").lower() else "image/svg+xml"
    else:
        q = max(1, min(100, WEBP_QUALITY))
        try:
            webp_bytes = _raster_bytes_to_webp(raw, q)
        except UnidentifiedImageError as exc:
            raise UploadValidationError(
                "Could not read image. Upload JPEG, PNG, GIF, WebP, BMP, or SVG."
            ) from exc
        except OSError as exc:
            raise UploadValidationError(f"Could not process image: {exc}") from exc
        except Exception as exc:
            raise UploadValidationError("Could not convert image to WebP.") from exc

        file_ext = ".webp"
        upload_body = io.BytesIO(webp_bytes)
        upload_content_type = WEBP_CONTENT_TYPE

    object_key = f"uploads/{uuid4().hex}{file_ext}"

    try:
        upload_body.seek(0)
        s3_client.upload_fileobj(
            upload_body,
            s3_config["bucket"],
            object_key,
            ExtraArgs={"ContentType": upload_content_type},
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
