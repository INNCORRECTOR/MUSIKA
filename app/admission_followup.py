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
                "Scan to pay — UPI / QR (image in HTML email, or open this link):",
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
        f'<p style="margin:0 0 18px;font-size:18px;font-weight:700;color:#FFFFFF;">Hi {safe_first},</p>',
    ]
    if _payment_settings_has_public_details(payment_settings):
        ps = payment_settings
        if _payment_settings_has_bank_or_upi_text(ps):
            html_parts.append(
                '<div style="margin:0 0 18px;padding:14px 18px;background:linear-gradient(135deg,#2a0a12,#3a0d18);'
                'border-left:5px solid #E11D48;border-radius:12px;">'
                '<span style="font-size:24px;font-weight:900;letter-spacing:-0.02em;color:#FFFFFF;">Fee payment</span></div>'
            )
            html_parts.append(
                '<p style="margin:0 0 18px;font-size:16px;font-weight:600;color:#E5E7EB;">'
                "Please use the following bank / UPI details:</p>"
            )
            inner_pay: list[str] = [
                "<ul style=\"margin:0;padding:18px 22px 18px 28px;background:#181818;border-radius:14px;"
                "border:1px solid rgba(225,29,72,0.3);list-style-position:outside;font-size:16px;line-height:1.8;"
                'color:#E5E7EB;">'
            ]
            if ps is not None:
                if (ps.account_holder_name or "").strip():
                    inner_pay.append(
                        "<li style=\"margin-bottom:10px;\"><strong style=\"font-size:14px;color:#FB7185;text-transform:uppercase;"
                        'letter-spacing:0.05em;">Account name:</strong> '
                        f'<span style="font-weight:800;font-size:17px;color:#FFFFFF;">'
                        f"{html.escape(ps.account_holder_name.strip())}</span></li>"
                    )
                if (ps.bank_account_number or "").strip():
                    inner_pay.append(
                        "<li style=\"margin-bottom:10px;\"><strong style=\"font-size:14px;color:#FB7185;text-transform:uppercase;"
                        'letter-spacing:0.05em;">Bank A/C:</strong> '
                        f'<span style="font-weight:800;font-size:17px;color:#FFFFFF;letter-spacing:0.05em;">'
                        f"{html.escape(ps.bank_account_number.strip())}</span></li>"
                    )
                if (ps.bank_ifsc or "").strip():
                    inner_pay.append(
                        "<li style=\"margin-bottom:10px;\"><strong style=\"font-size:14px;color:#FB7185;text-transform:uppercase;"
                        'letter-spacing:0.05em;">IFSC:</strong> '
                        f'<span style="font-weight:800;font-size:17px;color:#FFFFFF;">'
                        f"{html.escape(ps.bank_ifsc.strip())}</span></li>"
                    )
                if (ps.upi_id or "").strip():
                    inner_pay.append(
                        "<li><strong style=\"font-size:14px;color:#FB7185;text-transform:uppercase;"
                        'letter-spacing:0.05em;">UPI ID:</strong> '
                        f'<span style="font-weight:800;font-size:17px;color:#FFFFFF;">'
                        f"{html.escape(ps.upi_id.strip())}</span></li>"
                    )
            inner_pay.append("</ul>")
            html_parts.append("".join(inner_pay))
        elif ps is not None and (ps.scanner_image_url or "").strip():
            html_parts.append(
                '<div style="margin:16px 0 0;padding:14px 18px;background:linear-gradient(135deg,#2a0a12,#3a0d18);'
                'border-radius:12px;border-left:5px solid #E11D48;">'
                '<span style="display:block;font-size:13px;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;'
                'color:#FB7185;margin-bottom:8px;">Fee payment</span>'
                'Use <strong style="font-size:19px;color:#FFFFFF;">Pay to scan</strong> at the top of this email.</div>'
            )
    else:
        html_parts.append(
            '<p style="margin:0 0 18px;padding:16px 18px;background:#181818;border-radius:12px;border-left:5px solid #E11D48;'
            'font-size:17px;font-weight:700;color:#E5E7EB;line-height:1.5;">For <strong style="color:#FB7185;">fee payment</strong>, please '
            "reply to this email or contact our office for bank/UPI details and next steps.</p>"
        )

    if disc or gr:
        html_parts.append(
            '<div style="margin-top:28px;">'
            '<p style="margin:0 0 10px;font-size:18px;font-weight:800;color:#FFFFFF;">Your enrolment</p>'
            '<ul style="margin:0;padding-left:20px;color:#E5E7EB;line-height:1.8;">'
        )
        if disc:
            html_parts.append(f"<li><strong style=\"color:#FB7185;\">Course:</strong> {html.escape(disc)}</li>")
        if gr:
            html_parts.append(f"<li><strong style=\"color:#FB7185;\">Grade:</strong> {html.escape(gr)}</li>")
        html_parts.append("</ul></div>")

    if rev is not None:
        if rev.fees_amount_inr is not None:
            amt = html.escape(str(rev.fees_amount_inr))
            html_parts.append(
                '<div style="margin:30px 0 0;padding:28px 20px;text-align:center;background:linear-gradient(145deg,#2a0a12,#111111);'
                'border:2px solid #E11D48;border-radius:16px;box-shadow:0 8px 30px rgba(225,29,72,0.2);">'
                '<span style="display:block;font-size:13px;font-weight:900;letter-spacing:0.18em;text-transform:uppercase;'
                'color:#FB7185;margin-bottom:12px;">Fees (INR)</span>'
                f'<span style="display:block;font-size:44px;font-weight:900;color:#FFFFFF;line-height:1.1;">&#8377;&nbsp;{amt}</span>'
                "</div>"
            )
    else:
        html_parts.append(
            '<p style="margin:20px 0 0;padding:20px 22px;background:#181818;border-radius:14px;'
            'border:2px dashed rgba(251,113,133,0.45);font-size:17px;font-weight:700;color:#E5E7EB;text-align:center;line-height:1.45;">'
            '<strong style="font-size:18px;color:#FFFFFF;">Office fee</strong><br />'
            '<span style="font-weight:700;font-size:15px;color:#9CA3AF;">Amount will appear once entered in admin.</span></p>'
        )

    html_parts.append(
        '<div style="margin:28px 0 0;padding:20px 22px;background:linear-gradient(135deg,#111111,#1a1a1a);'
        'border-radius:14px;border:2px solid #E11D48;">'
        '<p style="margin:0 0 10px;font-size:13px;font-weight:900;letter-spacing:0.14em;text-transform:uppercase;'
        'color:#FB7185;">After you pay</p>'
        '<p style="margin:0;font-size:17px;font-weight:700;color:#E5E7EB;line-height:1.7;">'
        'Please reply to <strong style="color:#FB7185;">this email</strong> with a screenshot of your payment '
        'and include <strong style="color:#FB7185;">your name</strong>.</p>'
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
            <td style="padding:0;background:linear-gradient(165deg,#000000 0%,#111111 55%,#1a1a1a 100%);">
              <p style="margin:0;padding:18px 16px 10px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:12px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#FB7185;text-align:center;">Pay to scan</p>
              <div style="padding:0 18px 24px;text-align:center;">
                <img src="{safe_img_src}" alt="UPI QR — scan to pay" width="320" style="max-width:92%;height:auto;display:inline-block;border-radius:16px;background:#ffffff;padding:12px;box-sizing:border-box;border:1px solid rgba(255,255,255,0.08);" />
              </div>
            </td>
          </tr>
"""

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#050505;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#050505;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#111111;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);box-shadow:0 10px 40px rgba(0,0,0,0.45);">
{scanner_banner_row}          <tr>
            <td style="padding:36px 30px 30px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.7;color:#E5E7EB;">
{inner}
              <p style="margin:34px 0 0;padding-top:24px;border-top:1px solid rgba(255,255,255,0.08);color:#9CA3AF;line-height:1.8;">
                The <strong style="color:#FFFFFF;">{safe_site}</strong> team<br />
                <span style="font-size:14px;color:#6B7280;">School of Music &amp; Arts — Dimapur, Nagaland</span>
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
