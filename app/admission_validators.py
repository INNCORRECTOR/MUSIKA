import re

_EMAIL_MAX_LEN = 254
# Pragmatic single-line email check (local@domain.tld)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_admission_email(raw: str, *, required: bool) -> tuple[str | None, str | None]:
    """Return (normalized_lowercase_email, None) or (None, error_message)."""
    s = (raw or "").strip()
    if not s:
        if required:
            return None, "Email is required."
        return None, None
    if len(s) > _EMAIL_MAX_LEN:
        return None, "Email is too long."
    if not _EMAIL_RE.match(s):
        return None, "Please enter a valid email address."
    return s.lower(), None
