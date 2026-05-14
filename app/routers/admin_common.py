import re
from urllib.parse import quote, unquote, urlparse

import jwt
from fastapi import Request, status
from fastapi.responses import RedirectResponse

from app.routers.auth import AUTH_COOKIE_NAME
from app.security import decode_access_token


def require_admin(request: Request) -> RedirectResponse | None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        payload = decode_access_token(token)
        if not payload.get("is_admin"):
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    except jwt.PyJWTError:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    return None


def extract_s3_object_key_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not parsed.netloc or not parsed.path:
        return None

    object_key = unquote(parsed.path.lstrip("/"))
    if not object_key or not object_key.startswith("uploads/"):
        return None
    return object_key


def normalize_whatsapp_input(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("wa.me/"):
        if lowered.startswith("wa.me/"):
            return f"https://{raw}"
        return raw

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return raw
    return f"https://wa.me/{digits}"


def whatsapp_me_url_from_phone(phone: str | None, *, text: str | None = None) -> str | None:
    """Build https://wa.me/<digits> for WhatsApp Web/App. 10-digit Indian mobiles get prefix 91."""
    raw = (phone or "").strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) == 10:
        digits = "91" + digits
    if len(digits) < 10:
        return None
    base = f"https://wa.me/{digits}"
    if text:
        return f"{base}?text={quote(text)}"
    return base
