"""Transactional email via SMTP (free tiers: Gmail app password, Outlook, provider SMTP, etc.)."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from app.content import SITE_NAME

logger = logging.getLogger(__name__)


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

    subject = f"Welcome — you're on the {SITE_NAME} list!"
    body_text = (
        f"Hi there,\n\n"
        f"We're really glad you're here. You're officially subscribed as a new newsletter subscriber — "
        f"welcome to the {SITE_NAME} community.\n\n"
        "From time to time we'll drop you an email with news about programs, events, admissions, "
        "scholarships, and what's happening at the school. No spam — just the good stuff.\n\n"
        "If you ever have a question, hit reply or reach out through our contact page on the website.\n\n"
        "Thanks again for signing up,\n"
        f"The {SITE_NAME} team\n"
        "School of Music & Arts — Dimapur, Nagaland\n"
    )
    body_html = (
        f"<html><body style=\"font-family:system-ui,Segoe UI,sans-serif;line-height:1.55;color:#111827;\">"
        f"<p>Hi there,</p>"
        "<p>We're really glad you're here. You're officially subscribed as a "
        "<strong>new newsletter subscriber</strong> — welcome to the "
        f"<strong>{SITE_NAME}</strong> community.</p>"
        "<p>From time to time we'll send you updates about programs, events, admissions, scholarships, "
        "and what's happening at the school. No spam — just the good stuff.</p>"
        "<p>If you ever have a question, feel free to reply to this email or reach out through our "
        "<strong>Contact</strong> page on the website.</p>"
        "<p>Thanks again for signing up,<br/>"
        f"The <strong>{SITE_NAME}</strong> team<br/>"
        "<span style=\"color:#4b5563;\">School of Music &amp; Arts — Dimapur, Nagaland</span></p>"
        "</body></html>"
    )

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
