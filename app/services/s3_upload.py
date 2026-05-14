import io
import os
import re
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps, UnidentifiedImageError

WEBP_QUALITY = int(os.getenv("UPLOAD_WEBP_QUALITY", "80"))
WEBP_CONTENT_TYPE = "image/webp"
PASSPORT_PHOTO_SIZE = (413, 531)
PASSPORT_PHOTO_MIN_EDGE = 300
PASSPORT_PHOTO_MAX_BYTES = 1 * 1024 * 1024
PASSPORT_PHOTO_QUALITY = int(os.getenv("PASSPORT_PHOTO_WEBP_QUALITY", "85"))

# Longest side in pixels before WebP encode (reduces CPU + S3 bytes). 0 = no resize.
_MAX_EDGE_STR = (os.getenv("UPLOAD_MAX_IMAGE_EDGE") or "2560").strip()
try:
    UPLOAD_MAX_IMAGE_EDGE = int(_MAX_EDGE_STR)
except ValueError:
    UPLOAD_MAX_IMAGE_EDGE = 2560

# WebP encoder effort 0–6; lower is faster (default 4 was tuned from 6).
try:
    UPLOAD_WEBP_METHOD = int(os.getenv("UPLOAD_WEBP_METHOD", "4"))
except ValueError:
    UPLOAD_WEBP_METHOD = 4
UPLOAD_WEBP_METHOD = max(0, min(6, UPLOAD_WEBP_METHOD))


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


def _downscale_if_needed(im: Image.Image, max_edge: int) -> Image.Image:
    """Shrink so width and height stay under max_edge (keeps aspect ratio)."""
    if max_edge <= 0:
        return im
    w, h = im.size
    if w <= max_edge and h <= max_edge:
        return im
    out = im.copy()
    out.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return out


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


def _raster_bytes_to_webp(
    raw: bytes,
    *,
    quality: int,
    method: int,
    max_edge: int,
) -> bytes:
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        if getattr(im, "is_animated", False):
            im.seek(0)
        prepared = _prepare_image_for_webp(im)
        prepared = _downscale_if_needed(prepared, max_edge)
        out = io.BytesIO()
        prepared.save(out, "WEBP", quality=quality, method=method)
        return out.getvalue()


def _require_s3_config(s3_config) -> None:
    if (
        not s3_config["access_key"]
        or not s3_config["secret_key"]
        or not s3_config["region"]
        or not s3_config["bucket"]
    ):
        raise UploadValidationError("Missing AWS configuration in .env")


def _build_s3_client(s3_config):
    return boto3.client(
        "s3",
        region_name=s3_config["region"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
    )


def _upload_prepared_image_body(upload_body, upload_content_type: str, file_ext: str, s3_config):
    _require_s3_config(s3_config)
    s3_client = _build_s3_client(s3_config)
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


def upload_image_and_get_url(file, s3_config):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise UploadValidationError("Only image files are allowed.")

    _require_s3_config(s3_config)

    raw = file.file.read()
    try:
        file.file.seek(0)
    except OSError:
        pass

    if not raw:
        raise UploadValidationError("Empty file.")

    filename = file.filename or ""
    content_type = file.content_type

    if _is_svg_upload(content_type, filename, raw):
        file_ext = ".svg"
        upload_body = io.BytesIO(raw)
        upload_content_type = content_type if "svg" in (content_type or "").lower() else "image/svg+xml"
    else:
        q = max(1, min(100, WEBP_QUALITY))
        try:
            webp_bytes = _raster_bytes_to_webp(
                raw,
                quality=q,
                method=UPLOAD_WEBP_METHOD,
                max_edge=UPLOAD_MAX_IMAGE_EDGE,
            )
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

    return _upload_prepared_image_body(upload_body, upload_content_type, file_ext, s3_config)


def _passport_photo_bytes_to_webp(raw: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if getattr(im, "is_animated", False):
                im.seek(0)
            if min(im.size) < PASSPORT_PHOTO_MIN_EDGE:
                raise UploadValidationError("Passport photo is too small. Please upload a clearer image.")

            prepared = ImageOps.exif_transpose(im)
            prepared = _prepare_image_for_webp(prepared)
            prepared = ImageOps.fit(
                prepared,
                PASSPORT_PHOTO_SIZE,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.45),
            )
            out = io.BytesIO()
            prepared.save(
                out,
                "WEBP",
                quality=max(1, min(100, PASSPORT_PHOTO_QUALITY)),
                method=UPLOAD_WEBP_METHOD,
            )
            return out.getvalue()
    except UploadValidationError:
        raise
    except UnidentifiedImageError as exc:
        raise UploadValidationError("Could not read passport photo. Upload JPEG, PNG, or WebP.") from exc
    except OSError as exc:
        raise UploadValidationError(f"Could not process passport photo: {exc}") from exc
    except Exception as exc:
        raise UploadValidationError("Could not prepare passport photo.") from exc


def upload_passport_photo_and_get_url(file, s3_config):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise UploadValidationError("Passport photo must be an image file.")

    _require_s3_config(s3_config)
    raw = file.file.read()
    try:
        file.file.seek(0)
    except OSError:
        pass

    if not raw:
        raise UploadValidationError("Passport photo is empty.")
    if len(raw) > PASSPORT_PHOTO_MAX_BYTES:
        raise UploadValidationError("Passport photo must be below 1 MB.")
    if _is_svg_upload(file.content_type, file.filename or "", raw):
        raise UploadValidationError("Passport photo must be a regular photo, not SVG.")

    webp_bytes = _passport_photo_bytes_to_webp(raw)
    return _upload_prepared_image_body(io.BytesIO(webp_bytes), WEBP_CONTENT_TYPE, ".webp", s3_config)


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
