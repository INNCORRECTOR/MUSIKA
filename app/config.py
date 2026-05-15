import os

from dotenv import load_dotenv

# Public asset host (Cloudflare Worker → S3). Override via CDN_PUBLIC_BASE_URL in .env.
DEFAULT_CDN_PUBLIC_BASE_URL = "https://assets.musika.co.in"

# Legacy direct S3 hostname (for rewriting stored URLs in DB).
LEGACY_S3_PUBLIC_HOST_PREFIX = "https://musikazctech.s3.ap-south-1.amazonaws.com/"


def get_s3_config():
    # Reload .env values so updates are picked up without code changes.
    load_dotenv(override=True)
    return {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_REGION"),
        "bucket": os.getenv("AWS_S3_BUCKET_NAME"),
    }


def get_cdn_public_base_url() -> str:
    """Base URL for browser-facing assets (no trailing slash)."""
    load_dotenv(override=True)
    raw = os.getenv("CDN_PUBLIC_BASE_URL")
    if raw is not None:
        base = raw.strip().rstrip("/")
        if base.lower() in ("", "false", "0", "none"):
            pass
        else:
            return base
    return DEFAULT_CDN_PUBLIC_BASE_URL


def legacy_s3_public_prefix() -> str | None:
    """Bucket-specific S3 URL prefix from env, if configured."""
    s3 = get_s3_config()
    bucket = s3.get("bucket") or ""
    region = s3.get("region") or ""
    if bucket and region:
        return f"https://{bucket}.s3.{region}.amazonaws.com/"
    return None


def build_public_asset_url(object_key: str) -> str:
    """Build the public URL stored in DB / shown in HTML (CDN when configured)."""
    key = (object_key or "").lstrip("/")
    return f"{get_cdn_public_base_url()}/{key}"


def normalize_stored_asset_url(url: str | None) -> str | None:
    """Rewrite legacy S3 URLs to the CDN host; leave other URLs unchanged."""
    if not url:
        return url
    trimmed = url.strip()
    if not trimmed:
        return url

    cdn = get_cdn_public_base_url()
    prefixes: list[str] = [LEGACY_S3_PUBLIC_HOST_PREFIX]
    dynamic = legacy_s3_public_prefix()
    if dynamic and dynamic not in prefixes:
        prefixes.append(dynamic)

    for prefix in prefixes:
        if trimmed.startswith(prefix):
            return f"{cdn}/{trimmed[len(prefix) :].lstrip('/')}"

    return trimmed
