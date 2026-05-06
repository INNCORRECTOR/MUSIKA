from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
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
from app.db import get_db
from app.mailer import send_newsletter_welcome_email
import json

from app.models import (
    Artist,
    ContactMessage,
    CourseFeeStructure,
    Event,
    GalleryGenre,
    GalleryImage,
    Media,
    NewsletterSubscription,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
        "title": "Faculty & Artists | MUSIKA",
        "description": "Meet MUSIKA faculty and artists shaping music education, live performance, and creative mentorship.",
    },
    "/course": {
        "title": "Music Courses | MUSIKA Dimapur",
        "description": "Explore MUSIKA music courses designed for beginners and advancing artists in production, vocals, and performance. Financial assistance for deserving and talented students." ,
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
        "/artist",
        "/course",
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
def artist(
    request: Request,
    artist_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    page = PAGE_CONTENTS["artist"]
    context = shared_context("/artist")

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
                "hero_image_url": artist_row.hero_image_url,
                "featured_media_type": artist_row.featured_media_type,
                "featured_media_url": artist_row.featured_media_url,
                "featured_media_thumbnail_url": artist_row.featured_media_thumbnail_url,
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
                    "image_url": image.image_url,
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
        db.add(NewsletterSubscription(email=normalized_email, is_active=True))
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
