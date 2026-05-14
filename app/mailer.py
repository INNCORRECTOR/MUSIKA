"""Transactional email via SMTP (free tiers: Gmail app password, Outlook, provider SMTP, etc.)."""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from app.content import BRAND_LOGO_URL, SITE_NAME

# Load .env from project root so SMTP vars work even when the server cwd is not the repo root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)


def _normalize_smtp_password(raw: str) -> str:
    """Gmail app passwords are 16 chars; Google often shows them as four groups with spaces."""
    s = (raw or "").strip()
    if not s:
        return ""
    compact = "".join(s.split())
    if len(compact) == 16 and compact.isalnum():
        return compact
    return s


def _normalize_from_header(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        s = s[1:-1].strip()
    return s


def _newsletter_welcome_html(site_name: str, logo_url: str) -> str:
    """Table-based layout for broad HTML email client support."""
    safe_name = html.escape(site_name)
    # Logo URL is a fixed constant; attribute-escape for robustness if it ever changes.
    safe_logo = html.escape(logo_url, quote=True)
    public_site = (os.getenv("PUBLIC_SITE_URL") or os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")
    cta_block = ""
    if public_site:
        safe_url = html.escape(public_site, quote=True)
        cta_block = (
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:28px 0 0;">'
            f'<tr><td style="border-radius:8px;background:#07090f;">'
            f'<a href="{safe_url}" style="display:inline-block;padding:12px 22px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">Visit our website</a>'
            f"</td></tr></table>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td align="center" style="padding:36px 28px 28px;background:linear-gradient(165deg,#07090f 0%,#121826 55%,#0d1118 100%);">
              <img src="{safe_logo}" alt="{safe_name}" width="168" style="display:block;max-width:168px;height:auto;border:0;margin:0 auto;" />
            
            </td>
          </tr>
          <tr>
            <td style="padding:36px 32px 32px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.65;color:#1d1d1d;">
              <p style="margin:0 0 16px;font-size:20px;font-weight:600;color:#111827;">You have joined our list</p>
              <p style="margin:0 0 16px;">Hi there,</p>
              <p style="margin:0 0 16px;">We&rsquo;re really glad you&rsquo;re here. You have officially subscribed as a new <strong>newsletter subscriber</strong> &mdash; welcome to the <strong>{safe_name}</strong> community.</p>
              <p style="margin:0 0 16px;">From time to time we&rsquo;ll send you updates about programs, events, admissions, scholarships, and what&rsquo;s happening at the school. No spam &mdash; just the good stuff.</p>
              <p style="margin:0;">If you ever have a question, reply to this email or reach out through our <strong>Contact</strong> page on the website.</p>
              {cta_block}
              <p style="margin:28px 0 0;padding-top:24px;border-top:1px solid #e5e7eb;color:#374151;">
                Thanks again for signing up,<br />
                <strong style="color:#111827;">The {safe_name} team</strong>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 28px 28px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;color:#6b7280;text-align:center;background:#f9fafb;border-top:1px solid #e5e7eb;">
              Dimapur, Nagaland &middot; {safe_name}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _smtp_send_message(msg: EmailMessage) -> tuple[bool, str | None]:
    """Send a fully built EmailMessage. Returns (True, None) or (False, error_message)."""
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        return False, "SMTP is not configured (set SMTP_HOST)."

    user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    password = _normalize_smtp_password(os.getenv("SMTP_PASSWORD") or "")
    if not user or not password:
        return False, "Set SMTP_USER and SMTP_PASSWORD to send email."

    port_str = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    use_ssl = (os.getenv("SMTP_USE_SSL") or "").strip().lower() in ("1", "true", "yes")
    use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() in ("1", "true", "yes")

    to_addr = msg["To"]
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(msg)
    except Exception as exc:
        logger.exception("SMTP failed sending to %s", to_addr)
        return False, str(exc) or "SMTP send failed."

    return True, None


def send_multipart_email(
    to_address: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> tuple[bool, str | None]:
    """
    Send HTML + plain multipart email using the same SMTP env vars as the newsletter.

    Returns (True, None) on success, or (False, short_error_message) on missing config or send failure.
    """
    to_address = (to_address or "").strip()
    if not to_address:
        return False, "Recipient address is missing."

    from_email = _normalize_from_header(
        os.getenv("NEWSLETTER_FROM_EMAIL") or os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USER") or ""
    )
    if not from_email:
        return False, "Set NEWSLETTER_FROM_EMAIL or SMTP_FROM_EMAIL (or SMTP_USER)."

    reply_to = (os.getenv("SMTP_REPLY_TO") or "").strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_address
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    return _smtp_send_message(msg)


def send_newsletter_welcome_email(to_address: str) -> None:
    """
    Send a thank-you message to a new (or reactivated) newsletter subscriber.

    Configure via environment:
      SMTP_HOST       — e.g. smtp.gmail.com
      SMTP_PORT       — default 587 (STARTTLS); use 465 with SMTP_USE_SSL=true
      SMTP_USER       — login username (often same as your mailbox email)
      SMTP_PASSWORD   — app password or SMTP password (never commit real values)
      SMTP_USE_TLS    — default true for plain SMTP + STARTTLS (port 587)
      SMTP_USE_SSL    — set true for SMTP_SSL (typical port 465)

    Optional:
      NEWSLETTER_FROM_EMAIL or SMTP_FROM_EMAIL — From address (defaults to SMTP_USER)
      SMTP_REPLY_TO     — Reply-To header
      PUBLIC_SITE_URL or SITE_PUBLIC_URL — optional; adds a “Visit our website” button (no trailing slash)

    If SMTP_HOST is missing or send fails, logs only (subscription already saved).
    """
    subject = f"Welcome — you have joined the {SITE_NAME} list!"
    body_text = (
        f"Hi there,\n\n"
        f"We're really glad you're here. You have officially subscribed as a new newsletter subscriber — "
        f"welcome to the {SITE_NAME} community.\n\n"
        "From time to time we'll drop you an email with news about programs, events, admissions, "
        "scholarships, and what's happening at the school. No spam — just the good stuff.\n\n"
        "If you ever have a question, hit reply or reach out through our contact page on the website.\n\n"
        "Thanks again for signing up,\n"
        f"The {SITE_NAME} team\n"
        "School of Music & Arts — Dimapur, Nagaland\n"
    )
    body_html = _newsletter_welcome_html(SITE_NAME, BRAND_LOGO_URL)

    ok, err = send_multipart_email(to_address, subject, body_text, body_html)
    if not ok:
        logger.warning(
            "Newsletter welcome email skipped for %s: %s",
            to_address,
            err or "unknown",
        )


def send_alert_admission_received(to_address: str) -> None:
    """
    Notify the admin inbox when a new admission application is submitted.

    Set ADMIN_ALERT_EMAIL to the address that should receive these alerts.
    Uses the same SMTP env vars as send_multipart_email. If send fails, logs only.
    """
    safe_name = html.escape(SITE_NAME)
    public_site = (os.getenv("PUBLIC_SITE_URL") or os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")
    admin_url = f"{public_site}/admin/admissions" if public_site else ""

    body_text = (
        "Hello,\n\n"
        "You have a new admission application. Log in to the admin panel (Admissions) to review it.\n\n"
    )
    if admin_url:
        body_text += f"Link: {admin_url}\n\n"
    body_text += f"— {SITE_NAME}"

    cta_block = ""
    if public_site:
        safe_href = html.escape(admin_url, quote=True)
        cta_block = (
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:22px 0 0;">'
            f'<tr><td style="border-radius:8px;background:#111827;">'
            f'<a href="{safe_href}" style="display:inline-block;padding:12px 22px;font-family:Segoe UI,Helvetica,Arial,sans-serif;'
            f'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">Open admissions</a>'
            f"</td></tr></table>"
        )

    subject = f"You have a new admission — {SITE_NAME}"

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td style="padding:32px 28px 28px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.65;color:#1d1d1d;">
              <p style="margin:0 0 16px;font-size:20px;font-weight:600;color:#111827;">You have a new admission</p>
              <p style="margin:0 0 16px;">Hello,</p>
              <p style="margin:0 0 16px;">Someone just submitted an admission application. Review it in the admin panel.</p>
              {cta_block}
              <p style="margin:28px 0 0;padding-top:22px;border-top:1px solid #e5e7eb;color:#374151;">
                <strong style="color:#111827;">{safe_name}</strong>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 28px 24px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;color:#6b7280;text-align:center;background:#f9fafb;border-top:1px solid #e5e7eb;">
              Automated message · Admissions alert
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    ok, err = send_multipart_email(to_address, subject, body_text, body_html)
    if not ok:
        logger.warning(
            "Admission alert email skipped for %s: %s",
            to_address,
            err or "unknown",
        )