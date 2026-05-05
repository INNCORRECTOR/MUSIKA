"""Transactional email via SMTP (free tiers: Gmail app password, Outlook, provider SMTP, etc.)."""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from app.content import BRAND_LOGO_URL, SITE_NAME

logger = logging.getLogger(__name__)


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
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        logger.warning(
            "Newsletter welcome email skipped: set SMTP_HOST (e.g. smtp.gmail.com) for (%s)",
            to_address,
        )
        return

    user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    if not user or not password:
        logger.warning(
            "Newsletter welcome email skipped: set SMTP_USER and SMTP_PASSWORD (%s)",
            to_address,
        )
        return

    port_str = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    use_ssl = (os.getenv("SMTP_USE_SSL") or "").strip().lower() in ("1", "true", "yes")
    use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() in ("1", "true", "yes")

    from_email = (
        os.getenv("NEWSLETTER_FROM_EMAIL") or os.getenv("SMTP_FROM_EMAIL") or user or ""
    ).strip()
    if not from_email:
        logger.warning(
            "Newsletter welcome email skipped: set NEWSLETTER_FROM_EMAIL or SMTP_FROM_EMAIL (%s)",
            to_address,
        )
        return

    reply_to = (os.getenv("SMTP_REPLY_TO") or "").strip()

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

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_address
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

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
    except Exception:
        logger.exception("SMTP failed sending newsletter welcome to %s", to_address)
