"""Admission application PDF — line-based printed form (not table/grid)."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from app.config import build_public_asset_url, normalize_stored_asset_url
from app.models import AdmissionApplication, AdmissionPaymentSettings

# PDF header logo only (site header still uses BRAND_LOGO_URL in app.content).
PDF_BRAND_LOGO_URL = build_public_asset_url("MUSIKA+logo.png")

_EMPTY_FIELD = "--"


def _as_text(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s == "-" else s


def _contact_slots(application: AdmissionApplication) -> list[str]:
    rows = sorted(application.contacts, key=lambda c: c.sort_order)
    out = [_as_text(c.contact_value) for c in rows[:4]]
    while len(out) < 4:
        out.append("")
    return out


def _guardian_line(application: AdmissionApplication) -> str:
    parts: list[str] = []
    if application.guardian_name and str(application.guardian_name).strip():
        parts.append(str(application.guardian_name).strip())
    if application.guardian_relation and str(application.guardian_relation).strip():
        parts.append(f"({str(application.guardian_relation).strip()})")
    return " ".join(parts)


def _office_accepted_display(application: AdmissionApplication) -> str:
    """Y/N from review.accepted, else infer from application.status, else Pending."""
    review = application.review
    if review is not None and review.accepted is True:
        return "Yes"
    if review is not None and review.accepted is False:
        return "No"
    st = (application.status or "").strip().lower()
    if st == "accepted":
        return "Yes"
    if st == "rejected":
        return "No"
    return "Pending"


def _fetch_url_bytes(url: str, *, timeout: int = 15, max_bytes: int = 8 * 1024 * 1024) -> bytes | None:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read(max_bytes)
    except OSError:
        return None


def _print_font_family() -> tuple[str, str, str]:
    """(family_name, regular_path_or_empty, bold_path_or_empty). Empty paths => use built-in Times."""
    spec = importlib.util.find_spec("fpdf")
    if not spec or not spec.origin:
        return "Times", "", ""
    root = Path(spec.origin).resolve().parent
    reg = bold = None
    for sub in ("font", "fonts"):
        for base in ("DejaVuSerif", "DejaVuSerifCondensed"):
            r = root / sub / f"{base}.ttf"
            b = root / sub / f"{base}-Bold.ttf"
            if r.is_file():
                reg = r
            if b.is_file():
                bold = b
            if reg:
                break
        if reg:
            break
    if reg:
        return "Print", str(reg), str(bold) if bold else str(reg)
    return "Times", "", ""


def _unicode_body_font_family() -> tuple[str, str, str]:
    """Sans fallback for glyphs Times cannot encode."""
    spec = importlib.util.find_spec("fpdf")
    if not spec or not spec.origin:
        return "Helvetica", "", ""
    root = Path(spec.origin).resolve().parent
    for sub in ("font", "fonts"):
        r = root / sub / "DejaVuSans.ttf"
        b = root / sub / "DejaVuSans-Bold.ttf"
        if r.is_file():
            bold_path = str(b) if b.is_file() else str(r)
            return "Body", str(r), bold_path
    return "Helvetica", "", ""


def _image_to_png_bytes(raw: bytes) -> bytes | None:
    try:
        with Image.open(BytesIO(raw)) as im:
            im.load()
            rgb = ImageOps.exif_transpose(im.convert("RGB"))
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue()
    except (OSError, ValueError, UnidentifiedImageError):
        return None


def _pdf_logo_png_on_white(raw: bytes) -> bytes | None:
    """Replace black / near-black banner background with white for the PDF header logo."""
    try:
        with Image.open(BytesIO(raw)) as im0:
            im0.load()
            im = ImageOps.exif_transpose(im0).convert("RGBA")
        w, h = im.size
        if w <= 0 or h <= 0:
            return None
        fill = (255, 255, 255, 255)
        thresh = 55
        for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            try:
                ImageDraw.floodfill(im, xy=corner, value=fill, thresh=thresh)
            except (ValueError, IndexError):
                pass
        canvas = Image.new("RGB", im.size, (255, 255, 255))
        canvas.paste(im, mask=im.split()[3])
        out = BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()
    except (OSError, ValueError, UnidentifiedImageError):
        return None


def _payment_settings_nonempty(ps: AdmissionPaymentSettings | None) -> bool:
    if ps is None:
        return False
    return bool(
        _as_text(ps.account_holder_name)
        or _as_text(ps.bank_account_number)
        or _as_text(ps.bank_ifsc)
        or _as_text(ps.upi_id)
        or (ps.scanner_image_url or "").strip()
    )


def _image_mm_contain(px_w: int, px_h: int, box_w_mm: float, box_h_mm: float) -> tuple[float, float]:
    if px_w <= 0 or px_h <= 0 or box_w_mm <= 0 or box_h_mm <= 0:
        return 0.0, 0.0
    ar = px_w / px_h
    box_ar = box_w_mm / box_h_mm
    if ar >= box_ar:
        disp_w = box_w_mm
        disp_h = box_w_mm / ar
    else:
        disp_h = box_h_mm
        disp_w = box_h_mm * ar
    return disp_w, disp_h


# Passport photo slot 35 × 45 mm (same aspect ratio as 630 × 810 px scans)
PASSPORT_PHOTO_W_MM = 35.0
PASSPORT_PHOTO_H_MM = 45.0
# Extra space below the title before the logo / photo band (mm ≈ a few screen px when previewed)
FIRST_PAGE_BAND_TOP_GAP_MM = 2.5
# Right-align in logo band, then nudge left so it does not hug the passport column.
LOGO_BAND_RIGHT_INSET_MM = 1.2
LOGO_NUDGE_LEFT_MM = 26.0# larger => logo sits further left in the band
FORM_NO_META_FS_DELTA = 1.0  # slightly smaller than body for top-left line
# Blank strip after Remarks, then "Date" / "Sign" row and rules underneath
SIGNATURE_AFTER_REMARKS_SPACE_MM = 12.0
SIGNATURE_LABEL_TO_LINE_MM = 5.5  # gap from label baseline down to signature rules
PAYMENT_QR_BOX_MM = 42.0  # embedded UPI/bank QR image


class _AdmissionFormPdf(FPDF):
    """Printed-form layout: labels + rules (underlines), no grid."""

    ML = 15.0
    MR = 15.0
    MT = 3.5  # tight top so more form fits on first page
    FS = 10.5
    TITLE_FS = 13.0
    LABEL_W = 52.0
    GAP_LABEL_VALUE = 1.2  # mm after caption before value / rule start
    LINE_GRAY = (168, 168, 168)
    RULE_W = 0.07

    def __init__(self) -> None:
        super().__init__(unit="mm", format="A4")
        self._inner = 210.0 - self.ML - self.MR
        fam, reg, bold = _print_font_family()
        self._f_print = fam
        self._f_fallback = "Helvetica"
        if reg and fam == "Print":
            try:
                self.add_font("Print", "", reg)
                self.add_font("Print", "B", bold or reg)
            except OSError:
                self._f_print = "Times"

        bf_fam, bf_r, bf_b = _unicode_body_font_family()
        if bf_r:
            try:
                self.add_font("Body", "", bf_r)
                self.add_font("Body", "B", bf_b or bf_r)
                self._f_fallback = "Body"
            except OSError:
                self._f_fallback = "Helvetica"

        self.set_auto_page_break(True, margin=9)
        self.set_margins(self.ML, self.MT, self.MR)
        self.set_text_color(28, 28, 28)
        self.c_margin = 0.35

    def _value_x0(self) -> float:
        return self.ML + self.LABEL_W + self.GAP_LABEL_VALUE

    def _value_width(self) -> float:
        return self.ML + self._inner - self._value_x0()

    def _set(self, style: str = "", size: float | None = None) -> None:
        sz = size if size is not None else self.FS
        try:
            self.set_font(self._f_print, style, sz)
        except Exception:
            self.set_font("Times" if self._f_print == "Print" else self._f_fallback, style, sz)

    def _rule(self, x0: float, y: float, x1: float) -> None:
        self.set_draw_color(*self.LINE_GRAY)
        self.set_line_width(self.RULE_W)
        self.line(x0, y, x1, y)

    def form_no_top_left(self, number: str | int) -> None:
        """Compact single line: top-left, minimal vertical use."""
        fs = max(self.FS - FORM_NO_META_FS_DELTA, 8.0)
        self.set_xy(self.ML, self.MT)
        self._set("B", fs)
        self.cell(24, 3.6, "Form No.", align="L")
        self._set("", fs)
        txt = str(number)
        tw = self.get_string_width(txt) + 2
        self.cell(min(tw, self._inner - 28), 3.6, txt, align="L")

    def title_main(self, text: str) -> None:
        self.set_y(self.MT + 4.0)
        self._set("B", self.TITLE_FS)
        h = 5.6
        y0 = self.get_y()
        tw = self.get_string_width(text)
        self.cell(self._inner, h, text, align="C", new_x="LMARGIN", new_y="NEXT")
        y_rule = y0 + h - 1.0
        x0 = self.ML + (self._inner - tw) / 2
        self._rule(x0, y_rule, x0 + tw)
        self.ln(1.2)

    def section_heading(self, title: str) -> None:
        self.ln(2.0)
        self._set("B", self.FS + 0.4)
        t = title.upper()
        h = 5.0
        y0 = self.get_y()
        tw = self.get_string_width(t)
        self.cell(self._inner, h, t, align="C", new_x="LMARGIN", new_y="NEXT")
        y_rule = y0 + h - 0.9
        x0 = self.ML + (self._inner - tw) / 2
        self._rule(x0, y_rule, x0 + tw)
        self.ln(1.4)

    def field_line(self, label: str, value: str) -> None:
        """Label at left; value on wrapped lines; single rule under value zone."""
        lh = max(4.6, self.FS * 0.5)
        y_top = self.get_y()
        x_val = self._value_x0()
        w_val = self._value_width()

        self._set("B", self.FS)
        self.set_xy(self.ML, y_top)
        self.cell(self.LABEL_W, lh, label, align="L")

        self.set_xy(x_val, y_top)
        v = (value or "").strip()
        if not v:
            v = _EMPTY_FIELD

        drawn = False
        try:
            self.set_font(self._f_print, "", self.FS)
            self.multi_cell(w_val, lh, v, border=0, align="L")
            drawn = True
        except Exception:
            pass
        if not drawn:
            self.set_xy(x_val, y_top)
            self.set_font(self._f_fallback, "", self.FS)
            self.multi_cell(w_val, lh, v, border=0, align="L")

        y_bottom = self.get_y()
        rule_y = y_bottom + 0.35
        self._rule(x_val, rule_y, self.ML + self._inner)
        self.set_y(rule_y + 1.9)

    def field_line_optional(self, label: str, value: str) -> None:
        """Empty value: rule only, no '--' placeholder."""
        v = (value or "").strip()
        if not v:
            lh = max(4.6, self.FS * 0.5)
            y_top = self.get_y()
            x_val = self._value_x0()
            self._set("B", self.FS)
            self.set_xy(self.ML, y_top)
            self.cell(self.LABEL_W, lh, label, align="L")
            rule_y = y_top + lh
            self._rule(x_val, rule_y, self.ML + self._inner)
            self.set_y(rule_y + 1.9)
            return
        self.field_line(label, v)

    def field_block(self, label: str, value: str, *, empty_ok: bool = False) -> None:
        """Multiline / long text: label top-left, body with rule beneath."""
        lh = 4.4
        y_top = self.get_y()
        x_val = self._value_x0()
        w_val = self._value_width()

        self._set("B", self.FS)
        self.set_xy(self.ML, y_top)
        self.multi_cell(self.LABEL_W, lh, label, border=0, align="L")
        y_label = self.get_y()

        self.set_xy(x_val, y_top)
        raw = (value or "").strip()
        if not raw:
            if empty_ok:
                self.set_xy(x_val, y_top)
                try:
                    self.set_font(self._f_print, "", self.FS)
                except Exception:
                    self.set_font(self._f_fallback, "", self.FS)
                self.cell(w_val, lh, " ", align="L")
            else:
                self.set_xy(x_val, y_top)
                try:
                    self.set_font(self._f_print, "", self.FS)
                    self.multi_cell(w_val, lh, _EMPTY_FIELD, border=0, align="L")
                except Exception:
                    self.set_font(self._f_fallback, "", self.FS)
                    self.multi_cell(w_val, lh, _EMPTY_FIELD, border=0, align="L")
        else:
            try:
                self.set_font(self._f_print, "", self.FS)
                self.multi_cell(w_val, lh, raw, border=0, align="L")
            except Exception:
                self.set_xy(x_val, y_top)
                self.set_font(self._f_fallback, "", self.FS)
                self.multi_cell(w_val, lh, raw, border=0, align="L")

        y_body = self.get_y()
        y_rule = max(y_label, y_body) + 0.35
        # Rule only under the value area — no line through the bold label (Address, Special remarks, Remarks).
        self._rule(x_val, y_rule, self.ML + self._inner)
        self.set_y(y_rule + 2.0)

    def field_pair(self, la: str, va: str, lb: str, vb: str) -> None:
        """Two fields on one line; label width from text (avoids value overlapping long captions)."""
        gap = 5.5
        col_w = (self._inner - gap) / 2.0
        min_value_mm = 26.0
        lh = max(4.4, self.FS * 0.48)
        y_top = self.get_y()
        ends: list[float] = []

        def one(col_start: float, lab: str, val: str) -> None:
            x_lab = self.ML + col_start
            col_right = self.ML + col_start + col_w
            max_lab_w = max(col_w - min_value_mm, 30.0)

            self._set("B", self.FS)
            tw = self.get_string_width(lab) + 4.0

            if tw <= max_lab_w:
                lw_lab = max(tw, 19.0)
                self.set_xy(x_lab, y_top)
                self.cell(lw_lab, lh, lab, align="L")
                xv = x_lab + lw_lab
                y_label_bottom = y_top + lh
            else:
                self.set_xy(x_lab, y_top)
                self.multi_cell(max_lab_w, lh * 0.92, lab, border=0, align="L")
                y_label_bottom = self.get_y()
                xv = x_lab + max_lab_w

            wv = col_right - xv
            if wv < 14:
                xv = col_right - 14
                wv = 14

            v = (val or "").strip() or _EMPTY_FIELD
            self.set_xy(xv, y_top)
            try:
                self.set_font(self._f_print, "", self.FS)
                self.multi_cell(wv, lh, v, border=0, align="L")
            except Exception:
                self.set_xy(xv, y_top)
                self.set_font(self._f_fallback, "", self.FS)
                self.multi_cell(wv, lh, v, border=0, align="L")

            yb = self.get_y()
            yy = max(y_label_bottom, yb) + 0.35
            self._rule(xv, yy, col_right)
            ends.append(yy)

        one(0.0, la, va)
        self.set_y(y_top)
        one(col_w + gap, lb, vb)
        y_max = max(ends) if ends else y_top + lh
        self.set_y(y_max + 1.9)

    def signatures(self) -> None:
        """After Remarks: blank space, then Date … Sign on one row, rules underneath (classic form)."""
        self.ln(SIGNATURE_AFTER_REMARKS_SPACE_MM)

        gap = 22.0
        w = (self._inner - gap) / 2
        fs_sig = self.FS - 0.35
        self._set("B", fs_sig)
        y_label = self.get_y()

        tw_d = self.get_string_width("Date")
        tw_s = self.get_string_width("Sign")
        self.text(self.ML + (w - tw_d) / 2, y_label, "Date")
        self.text(self.ML + w + gap + (w - tw_s) / 2, y_label, "Sign")

        y_rule = y_label + SIGNATURE_LABEL_TO_LINE_MM
        self.set_draw_color(*self.LINE_GRAY)
        self.set_line_width(self.RULE_W)
        self.line(self.ML, y_rule, self.ML + w, y_rule)
        self.line(self.ML + w + gap, y_rule, self.ML + self._inner, y_rule)

        self.set_xy(self.ML, y_rule + 8)


def build_admission_application_pdf(
    application: AdmissionApplication,
    *,
    payment_settings: AdmissionPaymentSettings | None = None,
) -> bytes:
    pdf = _AdmissionFormPdf()
    pdf.add_page()
    inner = pdf._inner

    pdf.form_no_top_left(application.id)
    pdf.title_main("Application Form")
    pdf.ln(FIRST_PAGE_BAND_TOP_GAP_MM)

    photo_w = PASSPORT_PHOTO_W_MM
    logo_w = inner - photo_w - 5.0
    row_h = PASSPORT_PHOTO_H_MM
    LOGO_SCALE = 0.44  # smaller logo in band
    inset = 0.6
    y_top = pdf.get_y()
    x0 = pdf.ML

    # Logo: no box — image only, vertically centered in band
    logo_bytes = _fetch_url_bytes(PDF_BRAND_LOGO_URL)
    placed = False
    if logo_bytes:
        png = _pdf_logo_png_on_white(logo_bytes) or _image_to_png_bytes(logo_bytes)
        if png:
            try:
                with Image.open(BytesIO(png)) as im:
                    lw, lh = im.size
                if lw > 0 and lh > 0:
                    pad = 1.5
                    mw, mh = logo_w - 2 * pad, row_h - 2 * pad
                    iw = min(mw, mh * lw / lh)
                    ih = min(mh, mw * lh / lw)
                    iw *= LOGO_SCALE
                    ih *= LOGO_SCALE
                    # Toward passport photo, but not flush — slight gap via LOGO_NUDGE_LEFT_MM
                    logo_x = (
                        x0 + logo_w - iw - max(pad, LOGO_BAND_RIGHT_INSET_MM) - LOGO_NUDGE_LEFT_MM
                    )
                    logo_x = max(x0 + pad, logo_x)
                    pdf.image(
                        BytesIO(png),
                        x=logo_x,
                        y=y_top + (row_h - ih) / 2,
                        w=iw,
                        h=ih,
                    )
                    placed = True
            except OSError:
                pass
    if not placed:
        pdf.set_xy(x0, y_top + row_h / 2 - 2.5)
        pdf._set("", pdf.FS - 1.5)
        pdf.cell(logo_w, 5, "Logo", align="C")

    px = x0 + logo_w + 5.0
    pdf.set_draw_color(190, 190, 190)
    pdf.set_line_width(0.06)
    pdf.rect(px, y_top, photo_w, row_h)
    box_inner_w = photo_w - 2 * inset
    box_inner_h = row_h - 2 * inset
    ph_l = f"Photo\n{PASSPORT_PHOTO_W_MM:.0f}x{PASSPORT_PHOTO_H_MM:.0f}mm"
    passport_url = normalize_stored_asset_url(application.passport_photo_url)
    photo_raw = _fetch_url_bytes(passport_url) if passport_url else None
    if photo_raw:
        png_p = _image_to_png_bytes(photo_raw)
        if png_p:
            try:
                with Image.open(BytesIO(png_p)) as im:
                    lw, lh = im.size
                dw, dh = _image_mm_contain(lw, lh, box_inner_w, box_inner_h)
                if dw > 0 and dh > 0:
                    pdf.image(
                        BytesIO(png_p),
                        x=px + inset + (box_inner_w - dw) / 2,
                        y=y_top + inset + (box_inner_h - dh) / 2,
                        w=dw,
                        h=dh,
                    )
                else:
                    pdf.set_xy(px, y_top + row_h / 2 - 3.5)
                    pdf._set("", 7)
                    pdf.multi_cell(photo_w, 3.2, ph_l, align="C")
            except OSError:
                pdf.set_xy(px, y_top + row_h / 2 - 3.5)
                pdf._set("", 7)
                pdf.multi_cell(photo_w, 3.2, ph_l, align="C")
        else:
            pdf.set_xy(px, y_top + row_h / 2 - 3.5)
            pdf._set("", 7)
            pdf.multi_cell(photo_w, 3.2, ph_l, align="C")
    else:
        pdf.set_xy(px, y_top + row_h / 2 - 3.5)
        pdf._set("", 7)
        pdf.multi_cell(photo_w, 3.2, ph_l, align="C")

    pdf.set_y(y_top + row_h + 1.6)

    slots = _contact_slots(application)

    pdf.section_heading("Personal details")
    pdf.field_line("First name", _as_text(application.first_name))
    pdf.field_line("Last name", _as_text(application.last_name))
    pdf.field_pair("Gender", _as_text(application.gender), "Date of birth", _as_text(application.date_of_birth))
    pdf.field_line("Email", _as_text(application.email))
    pdf.field_pair("Contact 1", slots[0], "Contact 2", slots[1])
    pdf.field_pair("Contact 3", slots[2], "Contact 4", slots[3])
    pdf.field_line("Guardian / self", _guardian_line(application))
    pdf.field_line("Occupation (guardian)", _as_text(application.guardian_occupation))
    pdf.field_block(
        "Address & other details",
        _as_text(application.address_line),
        empty_ok=True,
    )
    pdf.field_line("City", _as_text(application.city))
    pdf.field_line("State", _as_text(application.state))
    pdf.field_line("PIN code", _as_text(application.pin_code))
    pdf.field_block("Special remarks", _as_text(application.special_remarks), empty_ok=False)

    pdf.section_heading("Course")
    pdf.field_line("Discipline", _as_text(application.discipline))
    pdf.field_line("Grade", _as_text(application.grade))
    pdf.field_line("Affiliated", _as_text(application.affiliated))
    pdf.field_line("Teacher", _as_text(application.preferred_teacher))

    pdf.section_heading("For office use only")
    review = application.review
    acc = _office_accepted_display(application)

    pdf.field_line("Accepted (Y/N)", acc)
    if review:
        pdf.field_line("Fees amount (INR)", _as_text(review.fees_amount_inr))
        pdf.field_pair(
            "Invoice no.",
            _as_text(review.invoice_no),
            "Invoice dated",
            _as_text(review.invoice_dated),
        )
        pdf.field_line("Payment (cash / cheque / online)", _as_text(review.payment_method))
        pdf.field_pair(
            "Course start date",
            _as_text(review.course_start_date),
            "Course duration",
            _as_text(review.course_duration),
        )
        pdf.field_line("Individual / group", _as_text(review.class_type))
        pdf.field_block("Remarks", _as_text(review.remarks), empty_ok=False)
    else:
        pdf.field_line_optional("Fees amount (INR)", "")
        pdf.field_line_optional("Invoice no.", "")
        pdf.field_line_optional("Invoice dated", "")
        pdf.field_line_optional("Payment (cash / cheque / online)", "")
        pdf.field_line_optional("Course start date", "")
        pdf.field_line_optional("Course duration", "")
        pdf.field_line_optional("Individual / group", "")
        pdf.field_line_optional("Remarks", "")

    pdf.signatures()

    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
