import os
import re
from datetime import date as dt_date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

# Same .env as mailer (project root), so ADMIN_ALERT_EMAIL / SMTP are visible regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from app.config import get_s3_config, normalize_stored_asset_url
from app.jinja_templates import templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.content import (
    BRAND_LOGO_URL,
    FOOTER_CREDIT_LOGO_URL,
    FOOTER_CREDIT_URL,
    FOOTER_FACEBOOK_URL,
    FOOTER_INSTAGRAM_URL,
    FOOTER_YOUTUBE_URL,
    NAV_ITEMS,
    PAGE_CONTENTS,
    SITE_NAME,
)
from app.admission_validators import normalize_admission_email
from app.db import get_db
from app.mailer import send_alert_admission_received, send_newsletter_welcome_email
import json

from app.models import (
    AdmissionApplication,
    AdmissionContact,
    AdmissionDiscipline,
    Artist,
    ContactMessage,
    CourseFeeStructure,
    Event,
    GalleryGenre,
    GalleryImage,
    Media,
    NewsletterSubscription,
)
from app.services.s3_upload import (
    UploadServiceError,
    UploadValidationError,
    delete_image_by_key,
    upload_passport_photo_and_get_url,
)

router = APIRouter()

_IN_MOBILE_SHORT = "Enter all 10 digits of the mobile number."
_IN_MOBILE_LONG = "Enter a 10-digit Indian mobile number (extra digits detected)."
_IN_MOBILE_START = "Indian mobile numbers start with 6, 7, 8, or 9."


def _normalize_indian_mobile(raw: str, *, required: bool) -> tuple[str | None, str | None]:
    """Parse optional/required Indian mobile; returns (+91XXXXXXXXXX, None) or (None, error)."""
    s = (raw or "").strip()
    if not s:
        if required:
            return None, "Mobile number is required."
        return None, None

    digits = re.sub(r"\D", "", s)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) < 10:
        return None, _IN_MOBILE_SHORT
    if len(digits) > 10:
        return None, _IN_MOBILE_LONG
    if digits[0] not in "6789":
        return None, _IN_MOBILE_START
    return f"+91{digits}", None


SEO_META = {
    "/": {
        "title": "MUSIKA - Music School in Dimapur, Nagaland",
        "description": "MUSIKA is a music school in Dimapur, Nagaland offering practical training, performances, and artist development programs.",
    },
    "/about": {
        "title": "About MUSIKA | Music Education in Dimapur",
        "description": "Learn about MUSIKA's mission, teaching approach, and creative music learning community in Dimapur, Nagaland.",
    },
    "/artist": {
        "title": "Faculty | MUSIKA",
        "description": "Meet MUSIKA faculty shaping music education, live performance, and creative mentorship.",
    },
    "/faculty": {
        "title": "Faculty | MUSIKA",
        "description": "Meet MUSIKA faculty shaping music education, live performance, and creative mentorship.",
    },
    "/course": {
        "title": "Music Courses | MUSIKA Dimapur",
        "description": "Explore MUSIKA music courses designed for beginners and advancing artists in production, vocals, and performance. Financial assistance for deserving and talented students." ,
    },
    "/admission": {
        "title": "Admission | MUSIKA School of Music",
        "description": "Apply for MUSIKA music programs by submitting the admission form online.",
    },
    "/event": {
        "title": "Music Events & Workshops | MUSIKA",
        "description": "Stay updated on MUSIKA live events, workshops, and community showcases in Dimapur, Nagaland.",
    },
    "/gallery": {
        "title": "Gallery | MUSIKA Performances & Moments",
        "description": "Browse MUSIKA gallery highlights from performances, studio sessions, workshops, and student milestones.",
    },
    "/contact": {
        "title": "Contact MUSIKA | Enquiry & Admissions",
        "description": "Contact MUSIKA for admissions, classes, artist opportunities, and partnership enquiries in Dimapur, Nagaland.",
    },
    "/privacy-policy": {
        "title": "Privacy Policy | MUSIKA",
        "description": "Read MUSIKA's privacy policy on how data is collected, used, and protected.",
    },
    "/terms": {
        "title": "Terms and Conditions | MUSIKA",
        "description": "Review MUSIKA terms and conditions for website access, programs, and services.",
    },
    "/cookies": {
        "title": "Cookie Policy | MUSIKA",
        "description": "Read MUSIKA's cookie policy explaining what cookies are used and why.",
    },
}


def _seo_meta_for_path(active_path: str) -> dict[str, str]:
    return SEO_META.get(active_path, {"title": SITE_NAME, "description": ""})


def shared_context(active_path: str):
    seo = _seo_meta_for_path(active_path)
    return {
        "site_name": SITE_NAME,
        "brand_logo_url": BRAND_LOGO_URL,
        "footer_credit_logo_url": FOOTER_CREDIT_LOGO_URL,
        "footer_credit_url": FOOTER_CREDIT_URL,
        "footer_facebook_url": FOOTER_FACEBOOK_URL,
        "footer_instagram_url": FOOTER_INSTAGRAM_URL,
        "footer_youtube_url": FOOTER_YOUTUBE_URL,
        "nav_items": NAV_ITEMS,
        "active_path": active_path,
        "seo_title": seo["title"],
        "seo_description": seo["description"],
    }


def load_artist_menu(db: Session):
    return [{"id": item.id, "name": item.name} for item in db.query(Artist).order_by(Artist.name.asc()).all()]


def load_course_mode_data(mode: str | None, db: Session):
    selected_mode = (mode or "offline").strip().lower()
    if selected_mode not in {"online", "offline"}:
        selected_mode = "offline"

    structure = (
        db.query(CourseFeeStructure)
        .filter(CourseFeeStructure.mode == selected_mode)
        .order_by(CourseFeeStructure.updated_at.desc())
        .first()
    )
    data = None
    if structure and structure.data_json:
        try:
            data = json.loads(structure.data_json)
        except json.JSONDecodeError:
            data = None
    return selected_mode, data


def load_admission_options(db: Session) -> list[dict]:
    try:
        disciplines = (
            db.query(AdmissionDiscipline)
            .options(selectinload(AdmissionDiscipline.grades), selectinload(AdmissionDiscipline.teachers))
            .filter(AdmissionDiscipline.is_active.is_(True))
            .order_by(AdmissionDiscipline.name.asc())
            .all()
        )
    except SQLAlchemyError:
        return []

    return [
        {
            "id": discipline.id,
            "name": discipline.name,
            "grades": [
                {"id": grade.id, "name": grade.name}
                for grade in discipline.grades
                if grade.is_active
            ],
            "teachers": [
                {"id": teacher.id, "name": teacher.name}
                for teacher in discipline.teachers
                if teacher.is_active
            ],
        }
        for discipline in disciplines
    ]


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/")
    context["artist_menu"] = load_artist_menu(db)

    return templates.TemplateResponse(
        request,
        "home.html",
        context,
    )


def render_independent_page(request: Request, template_name: str, slug: str, path: str, db: Session):
    page = PAGE_CONTENTS[slug]
    context = shared_context(path)
    context.update(
        {
            "title": page["title"],
            "intro": page["intro"],
            "sections": page["sections"],
            "artist_menu": load_artist_menu(db),
        }
    )
    return templates.TemplateResponse(request, template_name, context)


def _with_query(url: str, **params: str) -> str:
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _build_site_base_url(request: Request) -> str:
    """Prefer forwarded host/proto when deployed behind reverse proxies."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").strip()
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _optional_date_from_form(value: str | None) -> dt_date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return dt_date.fromisoformat(raw)


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/about")
    context["artist_menu"] = load_artist_menu(db)
    return templates.TemplateResponse(request, "about.html", context)


@router.get("/sitemap.xml")
def sitemap_xml(request: Request):
    base_url = _build_site_base_url(request)
    public_paths = [
        "/",
        "/about",
        "/faculty",
        "/artist",
        "/course",
        "/admission",
        "/event",
        "/gallery",
        "/contact",
        "/privacy-policy",
        "/terms",
        "/cookies",
    ]
    today = datetime.utcnow().date().isoformat()
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path in public_paths:
        xml_lines.extend(
            [
                "  <url>",
                f"    <loc>{base_url}{path}</loc>",
                f"    <lastmod>{today}</lastmod>",
                "  </url>",
            ]
        )
    xml_lines.append("</urlset>")
    return Response("\n".join(xml_lines), media_type="application/xml")


@router.get("/robots.txt")
def robots_txt(request: Request):
    base_url = _build_site_base_url(request)
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /admin/",
            "",
            f"Sitemap: {base_url}/sitemap.xml",
        ]
    )
    return Response(body, media_type="text/plain")


@router.get("/artist", response_class=HTMLResponse)
def artist_redirect(request: Request, artist_id: int | None = Query(default=None, ge=1)):
    url = "/faculty"
    if artist_id:
        url = _with_query(url, artist_id=str(artist_id))
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/faculty", response_class=HTMLResponse)
def faculty(
    request: Request,
    artist_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    page = PAGE_CONTENTS["artist"]
    context = shared_context("/faculty")

    artists = db.query(Artist).order_by(Artist.name.asc()).all()
    artist_ids = [item.id for item in artists]
    media_rows = []
    if artist_ids:
        media_rows = (
            db.query(Media)
            .filter(Media.artist_id.in_(artist_ids))
            .order_by(Media.created_at.desc())
            .all()
        )

    media_by_artist: dict[int, list[Media]] = {}
    for media in media_rows:
        media_by_artist.setdefault(media.artist_id, []).append(media)

    roster_items = []
    for artist_row in artists:
        items = media_by_artist.get(artist_row.id, [])
        images = [item for item in items if item.media_type == "image"]
        videos = [item for item in items if item.media_type == "video"]
        media_items = sorted(items, key=lambda item: item.created_at, reverse=True)
        cover_image = images[0] if images else None
        roster_items.append(
            {
                "id": artist_row.id,
                "name": artist_row.name,
                "title": artist_row.title,
                "bio": artist_row.bio,
                "hero_image_url": normalize_stored_asset_url(artist_row.hero_image_url),
                "featured_media_type": artist_row.featured_media_type,
                "featured_media_url": normalize_stored_asset_url(artist_row.featured_media_url),
                "featured_media_thumbnail_url": normalize_stored_asset_url(
                    artist_row.featured_media_thumbnail_url
                ),
                "facebook_url": artist_row.facebook_url,
                "instagram_url": artist_row.instagram_url,
                "twitter_url": artist_row.twitter_url,
                "whatsapp_url": artist_row.whatsapp_url,
                "email": artist_row.email,
                "youtube_url": artist_row.youtube_url,
                "spotify_url": artist_row.spotify_url,
                "youtube_music_url": artist_row.youtube_music_url,
                "amazon_music_url": artist_row.amazon_music_url,
                "imusic_url": artist_row.imusic_url,
                "images": images,
                "videos": videos,
                "media_items": media_items,
                "cover_image": cover_image,
                "media_count": len(items),
            }
        )

    selected_artist_id = artist_id
    featured_artist = None
    if roster_items:
        if selected_artist_id:
            featured_artist = next((item for item in roster_items if item["id"] == selected_artist_id), None)
        if not featured_artist:
            featured_artist = roster_items[0]
            selected_artist_id = featured_artist["id"]

    context.update(
        {
            "title": page["title"],
            "intro": page["intro"],
            "artists": roster_items,
            "featured_artist": featured_artist,
            "artist_menu": load_artist_menu(db),
            "selected_artist_id": selected_artist_id,
        }
    )
    return templates.TemplateResponse(request, "artist.html", context)


@router.get("/course", response_class=HTMLResponse)
def course(
    request: Request,
    mode: str | None = Query(default="offline"),
    db: Session = Depends(get_db),
):
    context = shared_context("/course")
    context["artist_menu"] = load_artist_menu(db)
    selected_mode, data = load_course_mode_data(mode, db)

    context.update(
        {
            "title": "Courses",
            "selected_mode": selected_mode,
            "course_data": data,
        }
    )
    return templates.TemplateResponse(request, "course.html", context)


@router.get("/admission", response_class=HTMLResponse)
def admission(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/admission")
    context["nav_highlight_path"] = "/course"
    context.update(
        {
            "artist_menu": load_artist_menu(db),
            "admission_options": load_admission_options(db),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse(request, "admission.html", context)


@router.post("/admission")
def submit_admission(
    background_tasks: BackgroundTasks,
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(default=""),
    date_of_birth: str = Form(default=""),
    email: str = Form(default=""),
    contact_1: str = Form(default=""),
    contact_2: str = Form(default=""),
    contact_3: str = Form(default=""),
    contact_4: str = Form(default=""),
    guardian_relation: str = Form(default=""),
    guardian_name: str = Form(default=""),
    guardian_occupation: str = Form(default=""),
    address_line: str = Form(default=""),
    city: str = Form(default=""),
    state_value: str = Form(default=""),
    pin_code: str = Form(default=""),
    special_remarks: str = Form(default=""),
    discipline: str = Form(default=""),
    grade: str = Form(default=""),
    affiliated: str = Form(default=""),
    preferred_teacher: str = Form(default=""),
    passport_photo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    normalized_first_name = (first_name or "").strip()
    normalized_last_name = (last_name or "").strip()
    normalized_gender = (gender or "").strip()
    normalized_city = (city or "").strip()

    if not normalized_first_name or not normalized_last_name:
        return RedirectResponse(
            url=_with_query("/admission", error="Please fill first name and last name."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not normalized_gender or not (date_of_birth or "").strip():
        return RedirectResponse(
            url=_with_query("/admission", error="Please fill gender and date of birth."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    normalized_email, email_err = normalize_admission_email(email, required=True)
    if email_err:
        return RedirectResponse(
            url=_with_query("/admission", error=email_err),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    normalized_contacts: list[str] = []
    for raw, required in (
        (contact_1, True),
        (contact_2, False),
        (contact_3, False),
        (contact_4, False),
    ):
        phone, err = _normalize_indian_mobile(raw, required=required)
        if err:
            return RedirectResponse(
                url=_with_query("/admission", error=err),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if phone:
            normalized_contacts.append(phone)

    if not normalized_contacts:
        return RedirectResponse(
            url=_with_query("/admission", error="Please add at least one contact number."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not normalized_city:
        return RedirectResponse(
            url=_with_query("/admission", error="Please fill city."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        parsed_date_of_birth = _optional_date_from_form(date_of_birth)
    except ValueError:
        return RedirectResponse(
            url=_with_query("/admission", error="Please enter a valid date of birth."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    passport_photo_key: str | None = None
    passport_photo_url: str | None = None
    if passport_photo and passport_photo.filename:
        try:
            passport_photo_key, _, passport_photo_url = upload_passport_photo_and_get_url(
                passport_photo,
                get_s3_config(),
            )
        except UploadValidationError as exc:
            return RedirectResponse(
                url=_with_query("/admission", error=str(exc)),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            return RedirectResponse(
                url=_with_query("/admission", error=str(exc)),
                status_code=status.HTTP_303_SEE_OTHER,
            )

    application = AdmissionApplication(
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        gender=normalized_gender,
        date_of_birth=parsed_date_of_birth,
        email=normalized_email,
        guardian_name=(guardian_name or "").strip() or None,
        guardian_relation=(guardian_relation or "").strip() or None,
        guardian_occupation=(guardian_occupation or "").strip() or None,
        address_line=(address_line or "").strip() or None,
        city=normalized_city,
        state=(state_value or "").strip() or None,
        pin_code=(pin_code or "").strip() or None,
        special_remarks=(special_remarks or "").strip() or None,
        discipline=(discipline or "").strip() or None,
        grade=(grade or "").strip() or None,
        affiliated=(affiliated or "").strip() or None,
        preferred_teacher=(preferred_teacher or "").strip() or None,
        passport_photo_key=passport_photo_key,
        passport_photo_url=passport_photo_url,
        status="new",
        is_seen=False,
    )

    try:
        db.add(application)
        db.flush()
        db.add_all(
            [
                AdmissionContact(
                    admission_id=application.id,
                    contact_value=contact_value,
                    sort_order=index,
                )
                for index, contact_value in enumerate(normalized_contacts, start=1)
            ]
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if passport_photo_key:
            try:
                delete_image_by_key(passport_photo_key, get_s3_config())
            except (UploadValidationError, UploadServiceError):
                pass
        return RedirectResponse(
            url=_with_query("/admission", error="Database tables missing. Run admission_tables.sql first."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    admin_alert = (os.getenv("ADMIN_ALERT_EMAIL") or "").strip()
    if admin_alert:
        background_tasks.add_task(send_alert_admission_received, admin_alert)

    return RedirectResponse(
        url=_with_query(
            "/admission",
            message=(
                "Thank you! We have received your application. Please wait—we will reach out to you "
                "soon through WhatsApp and email."
            ),
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/course/partial", response_class=HTMLResponse)
def course_partial(
    request: Request,
    mode: str | None = Query(default="offline"),
    db: Session = Depends(get_db),
):
    selected_mode, data = load_course_mode_data(mode, db)
    return templates.TemplateResponse(
        request,
        "partials/course_fee_content.html",
        {
            "selected_mode": selected_mode,
            "course_data": data,
        },
    )


@router.get("/event", response_class=HTMLResponse)
def event(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/event")
    context["artist_menu"] = load_artist_menu(db)

    events = (
        db.query(Event)
        .options(selectinload(Event.images))
        .order_by(Event.event_date.asc(), Event.event_time.asc(), Event.id.asc())
        .all()
    )
    now = datetime.now()

    upcoming_events = []
    past_events = []
    for item in events:
        event_dt = datetime.combine(item.event_date, item.event_time)
        if event_dt >= now:
            upcoming_events.append(item)
        else:
            past_events.append(item)

    # Past events are typically shown latest first.
    past_events.sort(key=lambda ev: (ev.event_date, ev.event_time, ev.id), reverse=True)

    context.update(
        {
            "title": "Events",
            "intro": "Explore upcoming performances, showcases, workshops, and community music gatherings by MUSIK-A.",
            "upcoming_events": upcoming_events,
            "past_events": past_events,
            "now": now,
        }
    )
    return templates.TemplateResponse(request, "event.html", context)


@router.get("/gallery", response_class=HTMLResponse)
def gallery(
    request: Request,
    genre: str | None = Query(default=None),
    limit: int = Query(default=9, ge=9, le=180),
    db: Session = Depends(get_db),
):
    page = PAGE_CONTENTS["gallery"]
    context = shared_context("/gallery")

    genres = db.query(GalleryGenre).order_by(GalleryGenre.name.asc()).all()
    images_query = (
        db.query(GalleryImage, GalleryGenre.slug)
        .join(GalleryGenre, GalleryGenre.id == GalleryImage.genre_id)
        .filter(GalleryImage.is_active.is_(True))
    )
    if genre:
        images_query = images_query.filter(GalleryGenre.slug == genre.strip().lower())
    total_images = images_query.count()
    latest_images = images_query.order_by(GalleryImage.created_at.desc()).limit(limit).all()

    context.update(
        {
            "title": page["title"],
            "intro": page["intro"],
            "artist_menu": load_artist_menu(db),
            "selected_genre": genre,
            "page_size": 9,
            "genres": [{"name": item.name, "slug": item.slug} for item in genres],
            "has_more_initial": total_images > len(latest_images),
            "images": [
                {
                    "image_url": normalize_stored_asset_url(image.image_url),
                    "caption": image.caption or "",
                    "genre": genre_slug,
                    "created_at": image.created_at,
                }
                for image, genre_slug in latest_images
            ],
        }
    )
    return templates.TemplateResponse(request, "gallery.html", context)


@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request, db: Session = Depends(get_db)):
    page = PAGE_CONTENTS["contact"]
    context = shared_context("/contact")
    context.update(
        {
            "title": page["title"],
            "intro": page["intro"],
            "sections": page["sections"],
            "artist_menu": load_artist_menu(db),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse(request, "contact.html", context)


@router.post("/contact/message")
def submit_contact_message(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(default=""),
    subject: str = Form(default=""),
    message: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_name = (name or "").strip()
    normalized_email = (email or "").strip().lower()
    normalized_message = (message or "").strip()

    if not normalized_name or not normalized_email or not normalized_message:
        return RedirectResponse(
            url=_with_query("/contact", error="Please fill name, email, and message."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    payload = ContactMessage(
        name=normalized_name,
        email=normalized_email,
        phone=(phone or "").strip() or None,
        subject=(subject or "").strip() or None,
        message=normalized_message,
        is_seen=False,
    )
    try:
        db.add(payload)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            url=_with_query("/contact", error="Database tables missing. Run contact_newsletter_tables.sql first."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=_with_query("/contact", message="Thanks! Your message has been received."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/newsletter/subscribe")
def newsletter_subscribe(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    privacy: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    normalized_email = (email or "").strip().lower()
    redirect_to = request.headers.get("referer") or "/"

    if not normalized_email or "@" not in normalized_email:
        return RedirectResponse(
            url=_with_query(redirect_to, newsletter_error="Please enter a valid email."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if privacy not in ("on", "1", "true", "yes"):
        return RedirectResponse(
            url=_with_query(
                redirect_to,
                newsletter_error="Please accept the Privacy Policy to subscribe.",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        existing = db.query(NewsletterSubscription).filter(NewsletterSubscription.email == normalized_email).first()
    except SQLAlchemyError:
        return RedirectResponse(
            url=_with_query(
                redirect_to,
                newsletter_error="Database tables missing. Run contact_newsletter_tables.sql first.",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.is_seen = False
            try:
                db.add(existing)
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                return RedirectResponse(
                    url=_with_query(
                        redirect_to,
                        newsletter_error="Database tables missing. Run contact_newsletter_tables.sql first.",
                    ),
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            background_tasks.add_task(send_newsletter_welcome_email, normalized_email)
        return RedirectResponse(
            url=_with_query(redirect_to, newsletter_message="You are already subscribed."),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        db.add(NewsletterSubscription(email=normalized_email, is_active=True, is_seen=False))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            url=_with_query(
                redirect_to,
                newsletter_error="Database tables missing. Run contact_newsletter_tables.sql first.",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    background_tasks.add_task(send_newsletter_welcome_email, normalized_email)
    return RedirectResponse(
        url=_with_query(redirect_to, newsletter_message="Thanks for subscribing to our newsletter!"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/privacy-policy")
    context["artist_menu"] = load_artist_menu(db)
    return templates.TemplateResponse(request, "legal_privacy.html", context)


@router.get("/terms", response_class=HTMLResponse)
def terms_and_conditions(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/terms")
    context["artist_menu"] = load_artist_menu(db)
    return templates.TemplateResponse(request, "legal_terms.html", context)


@router.get("/cookies", response_class=HTMLResponse)
def cookie_policy(request: Request, db: Session = Depends(get_db)):
    context = shared_context("/cookies")
    context["artist_menu"] = load_artist_menu(db)
    return templates.TemplateResponse(request, "legal_cookies.html", context)
