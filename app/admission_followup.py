"""Shared admission follow-up copy for WhatsApp and email (same substance, different formatting)."""

from __future__ import annotations

import html

from app.content import SITE_NAME
from app.models import AdmissionApplication, AdmissionPaymentSettings

# After-payment instructions — same meaning on both channels (email = reply here; WhatsApp = this chat).
SCREENSHOT_AFTER_PAYMENT_EMAIL_PLAIN = (
    "After you pay, please reply to this email with a screenshot of your payment and include your name."
)
# WhatsApp: same steps as the email — screenshot + name; channel is *this chat* instead of this email.
SCREENSHOT_AFTER_PAYMENT_WHATSAPP = (
    "*After you pay,* please send a screenshot of your payment *in this chat* and include *your name*."
)


def _wa_text(value: object | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    lowered = s.lower()
    if lowered in ("none", "null", "-", "--", "n/a", "na", "select", "dated"):
        return None
    return s


def _payment_settings_has_public_details(ps: AdmissionPaymentSettings | None) -> bool:
    if ps is None:
        return False
    return bool(
        (ps.account_holder_name or "").strip()
        or (ps.bank_account_number or "").strip()
        or (ps.bank_ifsc or "").strip()
        or (ps.upi_id or "").strip()
        or (ps.scanner_image_url or "").strip()
    )


def _payment_settings_has_bank_or_upi_text(ps: AdmissionPaymentSettings | None) -> bool:
    if ps is None:
        return False
    return bool(
        (ps.account_holder_name or "").strip()
        or (ps.bank_account_number or "").strip()
        or (ps.bank_ifsc or "").strip()
        or (ps.upi_id or "").strip()
    )


def build_whatsapp_message_body(
    application: AdmissionApplication,
    payment_settings: AdmissionPaymentSettings | None,
) -> str:
    """Prefilled text for admin wa.me links (*bold*, _italic_; truncated for URL limits)."""
    first = (application.first_name or "").strip() or "there"
    blocks: list[str] = [f"*Hi {first},*"]

    if _payment_settings_has_public_details(payment_settings):
        ps = payment_settings
        pay_lines: list[str] = [
            "*Fee payment*",
            "_Please use the following bank / UPI details:_",
            "",
        ]
        if ps is not None:
            if (ps.account_holder_name or "").strip():
                pay_lines.append(f"*Account name:* {ps.account_holder_name.strip()}")
            if (ps.bank_account_number or "").strip():
                pay_lines.append(f"*Bank A/C:* {ps.bank_account_number.strip()}")
            if (ps.bank_ifsc or "").strip():
                pay_lines.append(f"*IFSC:* {ps.bank_ifsc.strip()}")
            if (ps.upi_id or "").strip():
                pay_lines.append(f"*UPI ID:* {ps.upi_id.strip()}")
            if (ps.scanner_image_url or "").strip():
                pay_lines.append(f"*UPI / QR image:*\n{ps.scanner_image_url.strip()}")
        blocks.append("\n".join(pay_lines))
    else:
        blocks.append(
            "_For fee payment, please reply here or contact our office for bank/UPI details and next steps._"
        )

    course_lines: list[str] = []
    disc = _wa_text(application.discipline)
    gr = _wa_text(application.grade)
    if disc:
        course_lines.append(f"*Course:* {disc}")
    if gr:
        course_lines.append(f"*Grade:* {gr}")
    if course_lines:
        blocks.append("*Your enrolment*\n" + "\n".join(course_lines))

    rev = application.review
    if rev is not None:
        if rev.fees_amount_inr is not None:
            blocks.append(f"*Fees (INR):* {rev.fees_amount_inr}")
    else:
        blocks.append("_Office fee amount will appear once entered in admin._")

    blocks.append(SCREENSHOT_AFTER_PAYMENT_WHATSAPP)

    body = "\n\n".join(blocks)
    return body[:1800]


def build_admission_followup_email(
    application: AdmissionApplication,
    payment_settings: AdmissionPaymentSettings | None,
) -> tuple[str, str, str]:
    """Return (subject, text/plain, text/html) matching WhatsApp substance."""
    first = (application.first_name or "").strip() or "there"
    safe_first = html.escape(first)

    plain_lines: list[str] = [f"Hi {first},", ""]

    ps_top = payment_settings
    if ps_top is not None and (ps_top.scanner_image_url or "").strip():
        plain_lines.extend(
            [
                "Pay to scan — UPI / QR (image in HTML email, or open this link):",
                ps_top.scanner_image_url.strip(),
                "",
            ]
        )

    if _payment_settings_has_public_details(payment_settings):
        ps = payment_settings
        if _payment_settings_has_bank_or_upi_text(ps):
            plain_lines.append("Fee payment")
            plain_lines.append("Please use the following bank / UPI details:")
            plain_lines.append("")
            if ps is not None:
                if (ps.account_holder_name or "").strip():
                    plain_lines.append(f"Account name: {ps.account_holder_name.strip()}")
                if (ps.bank_account_number or "").strip():
                    plain_lines.append(f"Bank A/C: {ps.bank_account_number.strip()}")
                if (ps.bank_ifsc or "").strip():
                    plain_lines.append(f"IFSC: {ps.bank_ifsc.strip()}")
                if (ps.upi_id or "").strip():
                    plain_lines.append(f"UPI ID: {ps.upi_id.strip()}")
        elif ps is not None and (ps.scanner_image_url or "").strip():
            plain_lines.append('Fee payment: use "Pay to scan" above (QR image in HTML email).')
    else:
        plain_lines.append(
            "For fee payment, please reply to this email or contact our office for bank/UPI details and next steps."
        )

    plain_lines.append("")
    disc = _wa_text(application.discipline)
    gr = _wa_text(application.grade)
    if disc or gr:
        plain_lines.append("Your enrolment")
        if disc:
            plain_lines.append(f"Course: {disc}")
        if gr:
            plain_lines.append(f"Grade: {gr}")
        plain_lines.append("")

    rev = application.review
    if rev is not None:
        if rev.fees_amount_inr is not None:
            plain_lines.append(f"Fees (INR): {rev.fees_amount_inr}")
    else:
        plain_lines.append("Office fee amount will appear once entered in admin.")

    plain_lines.extend(
        [
            "",
            SCREENSHOT_AFTER_PAYMENT_EMAIL_PLAIN,
            "",
            "—",
            f"The {SITE_NAME} team",
            "School of Music & Arts — Dimapur, Nagaland",
        ]
    )
    plain = "\n".join(plain_lines)

    html_parts: list[str] = [
        f'<p style="margin:0 0 14px;font-size:17px;">Hi {safe_first},</p>',
    ]
    if _payment_settings_has_public_details(payment_settings):
        ps = payment_settings
        if _payment_settings_has_bank_or_upi_text(ps):
            html_parts.append(
                '<p style="margin:16px 0 10px;padding:12px 16px;background:linear-gradient(135deg,#fffbeb,#fef3c7);'
                "border-radius:10px;border-left:5px solid #f59e0b;font-size:22px;font-weight:900;color:#92400e;"
                'letter-spacing:-0.02em;">Fee payment</p>'
            )
            html_parts.append(
                '<p style="margin:0 0 14px;padding:0 4px;font-size:17px;font-weight:700;color:#1e293b;">'
                "Please use the following bank / UPI details:</p>"
            )
            inner_pay: list[str] = [
                "<ul style=\"margin:0;padding:14px 18px 14px 26px;background:#fffbeb;border-radius:10px;"
                "border:1px solid #fcd34d;list-style-position:outside;font-size:17px;line-height:1.55;"
                'color:#1e293b;">'
            ]
            if ps is not None:
                if (ps.account_holder_name or "").strip():
                    inner_pay.append(
                        "<li><strong style=\"font-size:15px;color:#b45309;\">Account name:</strong> "
                        f'<span style="font-weight:800;font-size:17px;color:#0f172a;">'
                        f"{html.escape(ps.account_holder_name.strip())}</span></li>"
                    )
                if (ps.bank_account_number or "").strip():
                    inner_pay.append(
                        "<li><strong style=\"font-size:15px;color:#b45309;\">Bank A/C:</strong> "
                        f'<span style="font-weight:800;font-size:17px;color:#0f172a;letter-spacing:0.04em;">'
                        f"{html.escape(ps.bank_account_number.strip())}</span></li>"
                    )
                if (ps.bank_ifsc or "").strip():
                    inner_pay.append(
                        "<li><strong style=\"font-size:15px;color:#b45309;\">IFSC:</strong> "
                        f'<span style="font-weight:800;font-size:17px;color:#0f172a;">'
                        f"{html.escape(ps.bank_ifsc.strip())}</span></li>"
                    )
                if (ps.upi_id or "").strip():
                    inner_pay.append(
                        "<li><strong style=\"font-size:15px;color:#b45309;\">UPI ID:</strong> "
                        f'<span style="font-weight:800;font-size:17px;color:#0f172a;">'
                        f"{html.escape(ps.upi_id.strip())}</span></li>"
                    )
            inner_pay.append("</ul>")
            html_parts.append("".join(inner_pay))
        elif ps is not None and (ps.scanner_image_url or "").strip():
            html_parts.append(
                '<p style="margin:16px 0 0;padding:14px 18px;background:linear-gradient(135deg,#fffbeb,#fef3c7);'
                'border-radius:12px;border:2px solid #fbbf24;font-size:18px;font-weight:800;color:#92400e;line-height:1.45;">'
                '<span style="display:block;font-size:13px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;'
                'color:#b45309;margin-bottom:6px;">Fee payment</span>'
                "Use <strong style=\"font-size:19px;color:#78350f;\">Pay to scan</strong> at the top of this email.</p>"
            )
    else:
        html_parts.append(
            '<p style="margin:0 0 14px;padding:14px 18px;background:#eff6ff;border-radius:12px;border-left:5px solid #3b82f6;'
            'font-size:17px;font-weight:700;color:#1e3a8a;line-height:1.5;">For <strong>fee payment</strong>, please reply '
            "to this email or contact our office for bank/UPI details and next steps.</p>"
        )

    if disc or gr:
        html_parts.append('<p style="margin:20px 0 8px;font-weight:700;">Your enrolment</p><ul style="margin:0;padding-left:20px;">')
        if disc:
            html_parts.append(f"<li><strong>Course:</strong> {html.escape(disc)}</li>")
        if gr:
            html_parts.append(f"<li><strong>Grade:</strong> {html.escape(gr)}</li>")
        html_parts.append("</ul>")

    if rev is not None:
        if rev.fees_amount_inr is not None:
            amt = html.escape(str(rev.fees_amount_inr))
            html_parts.append(
                '<div style="margin:22px 0 0;padding:22px 20px;text-align:center;background:linear-gradient(145deg,#fff7ed,#ffedd5);'
                'border:3px solid #fb923c;border-radius:14px;box-shadow:0 4px 14px rgba(251,146,60,0.25);">'
                '<span style="display:block;font-size:14px;font-weight:900;letter-spacing:0.16em;text-transform:uppercase;'
                'color:#c2410c;margin-bottom:10px;">Fees (INR)</span>'
                f'<span style="display:block;font-size:38px;font-weight:900;color:#9a3412;line-height:1.15;'
                f'text-shadow:0 1px 0 rgba(255,255,255,0.5);">&#8377;&nbsp;{amt}</span>'
                "</div>"
            )
    else:
        html_parts.append(
            '<p style="margin:20px 0 0;padding:16px 18px;background:#fefce8;border-radius:12px;border:2px dashed #eab308;'
            'font-size:17px;font-weight:800;color:#854d0e;text-align:center;line-height:1.45;">'
            "<strong style=\"font-size:18px;\">Office fee</strong><br />"
            '<span style="font-weight:700;font-size:15px;color:#a16207;">Amount will appear once entered in admin.</span></p>'
        )

    html_parts.append(
        '<div style="margin:24px 0 0;padding:18px 20px;background:linear-gradient(135deg,#ecfdf5,#d1fae5);'
        'border-radius:12px;border:2px solid #34d399;box-shadow:0 2px 10px rgba(16,185,129,0.15);">'
        '<p style="margin:0 0 8px;font-size:13px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;'
        'color:#047857;">After you pay</p>'
        '<p style="margin:0;font-size:17px;font-weight:800;color:#065f46;line-height:1.55;">'
        "Please reply to <strong style=\"color:#047857;\">this email</strong> with a screenshot of your payment "
        'and include <strong style="color:#047857;">your name</strong>.</p>'
        "</div>"
    )

    inner = "\n".join(html_parts)
    safe_site = html.escape(SITE_NAME)

    scanner_banner_row = ""
    ps_banner = payment_settings
    if ps_banner is not None and (ps_banner.scanner_image_url or "").strip():
        scan_url = ps_banner.scanner_image_url.strip()
        safe_img_src = html.escape(scan_url, quote=True)
        scanner_banner_row = f"""          <tr>
            <td style="padding:0;background:linear-gradient(165deg,#0b1220 0%,#1e293b 55%,#0f172a 100%);">
              <p style="margin:0;padding:18px 16px 10px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:12px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#cbd5e1;text-align:center;">Pay to scan</p>
              <div style="padding:0 18px 22px;text-align:center;">
                <img src="{safe_img_src}" alt="UPI QR — scan to pay" width="320" style="max-width:92%;height:auto;display:inline-block;border-radius:14px;background:#ffffff;padding:12px;box-sizing:border-box;border:1px solid rgba(148,163,184,0.35);" />
              </div>
            </td>
          </tr>
"""

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
{scanner_banner_row}          <tr>
            <td style="padding:32px 28px 28px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.65;color:#1d1d1d;">
{inner}
              <p style="margin:28px 0 0;padding-top:22px;border-top:1px solid #e5e7eb;color:#374151;">
                The <strong style="color:#111827;">{safe_site}</strong> team<br />
                <span style="font-size:14px;color:#6b7280;">School of Music &amp; Arts — Dimapur, Nagaland</span>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    subject = f"{SITE_NAME} — next steps for your application"
    return subject, plain, body_html
