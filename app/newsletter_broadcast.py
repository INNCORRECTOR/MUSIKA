"""Build admin newsletter broadcast emails (HTML + plain)."""

from __future__ import annotations

import html
import os
import re

from app.content import SITE_NAME

MAX_INLINE_IMAGES = 5


def _paragraphs_html(body_text: str) -> str:
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", (body_text or "").strip()):
        line = block.strip()
        if not line:
            continue
        safe = html.escape(line).replace("\n", "<br />")
        parts.append(f'<p style="margin:0 0 16px;">{safe}</p>')
    return "".join(parts) if parts else '<p style="margin:0 0 16px;">&nbsp;</p>'


def _header_banner_row(header_image_url: str | None) -> str:
    url = (header_image_url or "").strip()
    if not url:
        return ""
    safe_src = html.escape(url, quote=True)
    return f"""          <tr>
            <td style="padding:0;background:linear-gradient(165deg,#000000 0%,#111111 55%,#1a1a1a 100%);">
              <div style="padding:0;text-align:center;">
                <img src="{safe_src}" alt="" width="600" style="max-width:100%;height:auto;display:block;border:0;margin:0 auto;" />
              </div>
            </td>
          </tr>
"""


def _inline_images_html(urls: list[str]) -> str:
    blocks: list[str] = []
    for url in urls:
        u = (url or "").strip()
        if not u:
            continue
        safe_src = html.escape(u, quote=True)
        blocks.append(
            '<div style="margin:20px 0 0;text-align:center;">'
            f'<img src="{safe_src}" alt="" style="max-width:100%;height:auto;border-radius:12px;display:inline-block;" />'
            "</div>"
        )
    return "".join(blocks)


def build_newsletter_broadcast_email(
    subject: str,
    body_text: str,
    *,
    header_image_url: str | None = None,
    inline_image_urls: list[str] | None = None,
) -> tuple[str, str, str]:
    """Return (subject, plain_text, html_body) for one subscriber."""
    subj = (subject or "").strip() or f"Newsletter — {SITE_NAME}"
    body = (body_text or "").strip()
    urls = [u.strip() for u in (inline_image_urls or []) if (u or "").strip()][:MAX_INLINE_IMAGES]

    plain_parts = ["Hi there,", "", body, ""]
    if header_image_url:
        plain_parts.extend(["Header image:", header_image_url.strip(), ""])
    if urls:
        plain_parts.append("Images:")
        plain_parts.extend(urls)
        plain_parts.append("")
    plain_parts.extend(
        [
            f"— The {SITE_NAME} team",
            "School of Music & Arts — Dimapur, Nagaland",
            "",
            "You received this because you subscribed to our newsletter on musika.co.in.",
        ]
    )
    plain = "\n".join(plain_parts)

    safe_site = html.escape(SITE_NAME)
    inner = _paragraphs_html(body) + _inline_images_html(urls)

    public_site = (os.getenv("PUBLIC_SITE_URL") or os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")
    cta_block = ""
    if public_site:
        safe_url = html.escape(public_site, quote=True)
        cta_block = (
            '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0 0;">'
            '<tr><td style="border-radius:8px;background:#E11D48;">'
            f'<a href="{safe_url}" style="display:inline-block;padding:12px 22px;font-family:Segoe UI,Helvetica,Arial,sans-serif;'
            'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">Visit our website</a>'
            "</td></tr></table>"
        )

    header_row = _header_banner_row(header_image_url)

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#050505;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#050505;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#111111;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);box-shadow:0 10px 40px rgba(0,0,0,0.45);">
{header_row}          <tr>
            <td style="padding:36px 30px 30px;font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.7;color:#E5E7EB;">
{inner}
              {cta_block}
              <p style="margin:34px 0 0;padding-top:24px;border-top:1px solid rgba(255,255,255,0.08);color:#9CA3AF;line-height:1.8;">
                The <strong style="color:#FFFFFF;">{safe_site}</strong> team<br />
                <span style="font-size:14px;color:#6B7280;">School of Music &amp; Arts — Dimapur, Nagaland</span>
              </p>
              <p style="margin:16px 0 0;font-size:13px;color:#6B7280;">You received this because you subscribed to our newsletter.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subj, plain, body_html
