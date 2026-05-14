from datetime import date as dt_date, time as dt_time
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload
import json

from app.admission_followup import build_admission_followup_email, build_whatsapp_message_body
from app.admission_validators import normalize_admission_email
from app.config import get_s3_config
from app.db import get_db
from app.models import (
    AdmissionAdminReview,
    AdmissionApplication,
    AdmissionContact,
    AdmissionDiscipline,
    AdmissionGrade,
    AdmissionPaymentSettings,
    AdmissionTeacher,
    Artist,
    ContactMessage,
    CourseFeeStructure,
    Event,
    EventImage,
    GalleryGenre,
    GalleryImage,
    Media,
    NewsletterSubscription,
    User,
)
from app.routers.admin_common import (
    extract_s3_object_key_from_url,
    normalize_whatsapp_input,
    require_admin,
    whatsapp_me_url_from_phone,
)
from app.routers.gallery_routes import slugify
from app.routers.auth import AUTH_COOKIE_NAME, shared_auth_context
from app.security import create_access_token, decode_access_token, verify_password
from app.mailer import send_multipart_email
from app.services.admission_pdf import build_admission_application_pdf
from app.services.s3_upload import (
    UploadServiceError,
    UploadValidationError,
    delete_image_by_key,
    upload_image_and_get_url,
    upload_passport_photo_and_get_url,
)
from app.routers.pages import load_admission_options

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _ensure_inbox_seen_columns(db: Session) -> None:
    # Schema changes are handled by migrations, not runtime request flow.
    return


def _optional_date_from_form(value: str | None) -> dt_date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return dt_date.fromisoformat(raw)


def _current_admin_user_id(request: Request) -> int | None:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        return None
    if not payload.get("is_admin"):
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def _download_filename_part(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part)


def _absolute_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _get_admission_payment_settings(db: Session) -> AdmissionPaymentSettings | None:
    try:
        return db.query(AdmissionPaymentSettings).filter(AdmissionPaymentSettings.id == 1).first()
    except SQLAlchemyError:
        return None


def _get_or_create_admission_payment_settings(db: Session) -> tuple[AdmissionPaymentSettings | None, str | None]:
    """Load singleton payment settings; create empty row if missing. Error if table absent."""
    try:
        row = db.query(AdmissionPaymentSettings).filter(AdmissionPaymentSettings.id == 1).first()
        if row is None:
            row = AdmissionPaymentSettings(id=1)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row, None
    except SQLAlchemyError:
        db.rollback()
        return None, "Payment settings unavailable. Run admission_tables.sql on the database (admission_payment_settings)."


def _inject_admin_inbox_counts(context: dict, db: Session) -> None:
    _ensure_inbox_seen_columns(db)
    try:
        unread_contact_count = (
            db.query(func.count(ContactMessage.id)).filter(ContactMessage.is_seen.is_(False)).scalar() or 0
        )
        unread_subscription_count = (
            db.query(func.count(NewsletterSubscription.id))
            .filter(NewsletterSubscription.is_seen.is_(False))
            .scalar()
            or 0
        )
        unread_admission_count = (
            db.query(func.count(AdmissionApplication.id))
            .filter(AdmissionApplication.is_seen.is_(False))
            .scalar()
            or 0
        )
    except SQLAlchemyError:
        unread_contact_count = 0
        unread_subscription_count = 0
        unread_admission_count = 0

    context.update(
        {
            "unread_contact_count": unread_contact_count,
            "unread_subscription_count": unread_subscription_count,
            "unread_admission_count": unread_admission_count,
            "unread_total_count": unread_contact_count + unread_subscription_count + unread_admission_count,
        }
    )


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(
        request, "admin_login.html", shared_auth_context(request, "Admin Login")
    )


@router.post("/admin/login", response_class=HTMLResponse)
def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Admin Login")
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if (
        not user
        or not user.is_active
        or not user.is_admin
        or not verify_password(password, user.password_bytes)
    ):
        context["error"] = "Invalid admin credentials."
        return templates.TemplateResponse(
            request, "admin_login.html", context, status_code=status.HTTP_401_UNAUTHORIZED
        )

    token = create_access_token({"sub": str(user.id), "email": user.email, "is_admin": True})
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_page.html", context)


@router.post("/admin/dashboard/genres")
def admin_create_genre(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    normalized_name = name.strip()
    slug = slugify(normalized_name)
    if not normalized_name or not slug:
        return RedirectResponse(
            url="/admin/gallery?error=Invalid+category+name", status_code=status.HTTP_303_SEE_OTHER
        )

    exists = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if exists:
        return RedirectResponse(
            url="/admin/gallery?error=Category+already+exists", status_code=status.HTTP_303_SEE_OTHER
        )

    genre = GalleryGenre(name=normalized_name, slug=slug)
    db.add(genre)
    db.commit()
    return RedirectResponse(
        url="/admin/gallery?message=Category+created+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/images")
def admin_upload_image(
    request: Request,
    genre_slug: str = Form(...),
    caption: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    slug = slugify(genre_slug)
    genre = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if not genre:
        return RedirectResponse(
            url="/admin/gallery?error=Category+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        object_key, _, public_image_url = upload_image_and_get_url(file, get_s3_config())
    except UploadValidationError as exc:
        return RedirectResponse(
            url=f"/admin/gallery?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        return RedirectResponse(
            url=f"/admin/gallery?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    image = GalleryImage(
        genre_id=genre.id,
        s3_key=object_key,
        image_url=public_image_url,
        caption=(caption or "").strip() or None,
        is_active=True,
    )
    db.add(image)
    db.commit()
    return RedirectResponse(
        url="/admin/gallery?message=Image+uploaded+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/admin/gallary", include_in_schema=False)
def admin_gallery_list_legacy_redirect(request: Request) -> RedirectResponse:
    query = str(request.url.query)
    target = "/admin/gallery" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.get("/admin/gallery", response_class=HTMLResponse)
def admin_gallery_page(
    request: Request,
    page: int = 1,
    page_size: int = 5,
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Admin Gallery")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    genres = db.query(GalleryGenre).order_by(GalleryGenre.name.asc()).all()
    safe_page_size = max(1, min(page_size, 100))
    total_uploads = db.query(func.count(GalleryImage.id)).filter(GalleryImage.is_active.is_(True)).scalar() or 0
    total_pages = max(1, (total_uploads + safe_page_size - 1) // safe_page_size)
    current_page = max(1, min(page, total_pages))
    offset = (current_page - 1) * safe_page_size

    paginated_images = (
        db.query(GalleryImage, GalleryGenre.slug)
        .join(GalleryGenre, GalleryGenre.id == GalleryImage.genre_id)
        .filter(GalleryImage.is_active.is_(True))
        .order_by(GalleryImage.created_at.desc())
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "genres": genres,
            "latest_images": paginated_images,
            "current_page": current_page,
            "total_pages": total_pages,
            "page_size": safe_page_size,
            "total_uploads": total_uploads,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": current_page - 1,
            "next_page": current_page + 1,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admingallery.html", context)


@router.get("/admin/gallary/categories/{genre_slug}", include_in_schema=False)
def admin_gallery_category_legacy_redirect(genre_slug: str, request: Request) -> RedirectResponse:
    query = str(request.url.query)
    base = f"/admin/gallery/categories/{genre_slug}"
    target = base + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.get("/admin/gallery/categories/{genre_slug}", response_class=HTMLResponse)
def admin_gallery_category_page(
    genre_slug: str,
    request: Request,
    page: int = 1,
    page_size: int = 8,
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Category Uploads")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    slug = slugify(genre_slug)
    genre = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if not genre:
        return RedirectResponse(
            url="/admin/gallery?error=Category+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    safe_page_size = max(1, min(page_size, 50))
    total_uploads = (
        db.query(func.count(GalleryImage.id))
        .filter(GalleryImage.genre_id == genre.id, GalleryImage.is_active.is_(True))
        .scalar()
        or 0
    )
    total_pages = max(1, (total_uploads + safe_page_size - 1) // safe_page_size)
    current_page = max(1, min(page, total_pages))
    offset = (current_page - 1) * safe_page_size

    category_images = (
        db.query(GalleryImage)
        .filter(GalleryImage.genre_id == genre.id, GalleryImage.is_active.is_(True))
        .order_by(GalleryImage.created_at.desc())
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "genre": genre,
            "category_images": category_images,
            "current_page": current_page,
            "total_pages": total_pages,
            "page_size": safe_page_size,
            "total_uploads": total_uploads,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": current_page - 1,
            "next_page": current_page + 1,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admingallery_category.html", context)


@router.post("/admin/dashboard/images/{image_id}/delete")
def admin_delete_image(
    image_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    return_to = request.query_params.get("return_to")

    image = db.query(GalleryImage).filter(GalleryImage.id == image_id).first()
    if not image:
        target_url = return_to or "/admin/gallery"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error=Image+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        delete_image_by_key(image.s3_key, get_s3_config())
    except UploadValidationError as exc:
        target_url = return_to or "/admin/gallery"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        target_url = return_to or "/admin/gallery"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.delete(image)
    db.commit()
    target_url = return_to or "/admin/gallery"
    separator = "&" if "?" in target_url else "?"
    return RedirectResponse(
        url=f"{target_url}{separator}message=Image+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/dashboard/categories/{genre_id}/delete")
def admin_delete_category(
    genre_id: int,
    request: Request,
    delete_confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    genre = db.query(GalleryGenre).filter(GalleryGenre.id == genre_id).first()
    if not genre:
        return RedirectResponse(
            url="/admin/gallery?error=Category+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    expected_confirmation = f"delete {genre.name}".strip().lower()
    provided_confirmation = (delete_confirmation or "").strip().lower()
    if provided_confirmation != expected_confirmation:
        return RedirectResponse(
            url="/admin/gallery?error=Delete+confirmation+did+not+match.+Use+delete+" + genre.name.replace(" ", "+"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    linked_images = db.query(GalleryImage).filter(GalleryImage.genre_id == genre.id).all()
    try:
        for image in linked_images:
            delete_image_by_key(image.s3_key, get_s3_config())
    except UploadValidationError as exc:
        return RedirectResponse(
            url=f"/admin/gallery?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        return RedirectResponse(
            url=f"/admin/gallery?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.delete(genre)
    db.commit()
    return RedirectResponse(
        url="/admin/gallery?message=Category+deleted+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/admin/artist", response_class=HTMLResponse)
@router.get("/admin/artists", response_class=HTMLResponse)
def admin_artist_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Artist")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    artists = (
        db.query(Artist, func.count(Media.id).label("media_count"))
        .outerjoin(Media, Media.artist_id == Artist.id)
        .group_by(Artist.id)
        .order_by(Artist.created_at.desc())
        .all()
    )
    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "artists": artists,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "adminartist.html", context)


@router.get("/admin/artist/{artist_id}/media", response_class=HTMLResponse)
@router.get("/admin/artists/{artist_id}/media", response_class=HTMLResponse)
def admin_artist_media_page(
    artist_id: int,
    request: Request,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Artist Media")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        return RedirectResponse(
            url="/admin/artist?error=Artist+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    safe_page_size = max(1, min(page_size, 50))
    total_media = db.query(func.count(Media.id)).filter(Media.artist_id == artist.id).scalar() or 0
    total_pages = max(1, (total_media + safe_page_size - 1) // safe_page_size)
    current_page = max(1, min(page, total_pages))
    offset = (current_page - 1) * safe_page_size

    media_items = (
        db.query(Media)
        .filter(Media.artist_id == artist.id)
        .order_by(Media.created_at.desc())
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )

    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "artist": artist,
            "media_items": media_items,
            "current_page": current_page,
            "total_pages": total_pages,
            "page_size": safe_page_size,
            "total_media": total_media,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": current_page - 1,
            "next_page": current_page + 1,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "adminartist_media.html", context)


@router.get("/admin/courses", response_class=HTMLResponse)
def admin_courses_page(request: Request, mode: str = "offline", db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Courses")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    selected_mode = (mode or "offline").strip().lower()
    if selected_mode not in {"online", "offline"}:
        selected_mode = "offline"

    structure = (
        db.query(CourseFeeStructure)
        .filter(CourseFeeStructure.mode == selected_mode)
        .order_by(CourseFeeStructure.updated_at.desc())
        .first()
    )
    loaded_data = None
    if structure and structure.data_json:
        try:
            loaded_data = json.loads(structure.data_json)
        except json.JSONDecodeError:
            loaded_data = None

    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "selected_mode": selected_mode,
            "loaded_data": loaded_data,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admincourses.html", context)


@router.post("/admin/dashboard/courses/{mode}")
def admin_save_courses(
    request: Request,
    mode: str,
    page_title: str = Form(default=""),
    data_json: str = Form(...),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    selected_mode = (mode or "offline").strip().lower()
    if selected_mode not in {"online", "offline"}:
        selected_mode = "offline"

    raw = (data_json or "").strip()
    if not raw:
        return RedirectResponse(
            url=f"/admin/courses?mode={selected_mode}&error=Missing+course+structure+data",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return RedirectResponse(
            url=f"/admin/courses?mode={selected_mode}&error=Invalid+JSON+data",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not isinstance(parsed, dict) or not isinstance(parsed.get("sections", []), list):
        return RedirectResponse(
            url=f"/admin/courses?mode={selected_mode}&error=Invalid+structure+format",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    existing = (
        db.query(CourseFeeStructure)
        .filter(CourseFeeStructure.mode == selected_mode)
        .order_by(CourseFeeStructure.updated_at.desc())
        .first()
    )
    if existing:
        existing.title = (page_title or "").strip() or parsed.get("pageTitle") or f"{selected_mode.upper()} FEE STRUCTURES"
        existing.data_json = raw
    else:
        db.add(
            CourseFeeStructure(
                mode=selected_mode,
                title=(page_title or "").strip() or parsed.get("pageTitle") or f"{selected_mode.upper()} FEE STRUCTURES",
                data_json=raw,
            )
        )
    db.commit()
    return RedirectResponse(
        url=f"/admin/courses?mode={selected_mode}&message={selected_mode.capitalize()}+course+structure+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/admin/events", response_class=HTMLResponse)
@router.get("/admin/event", response_class=HTMLResponse)
def admin_events_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Events")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    events = (
        db.query(Event)
        .options(selectinload(Event.images))
        .order_by(Event.event_date.desc(), Event.event_time.desc(), Event.id.desc())
        .all()
    )
    context.update(
        {
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
            "events": events,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "adminevent.html", context)


@router.get("/admin/inbox", response_class=HTMLResponse)
def admin_inbox_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Inbox")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    _ensure_inbox_seen_columns(db)
    try:
        messages = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(200).all()
        db.query(ContactMessage).filter(ContactMessage.is_seen.is_(False)).update(
            {ContactMessage.is_seen: True},
            synchronize_session=False,
        )
        db.commit()
        inbox_error = None
    except SQLAlchemyError:
        db.rollback()
        messages = []
        inbox_error = "Database tables missing. Run contact_newsletter_tables.sql first."
    context.update(
        {
            "messages": messages,
            "error": inbox_error,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_inbox.html", context)


@router.get("/admin/subscribers", response_class=HTMLResponse)
def admin_subscribers_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Subscribers")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    _ensure_inbox_seen_columns(db)
    try:
        subscriptions = (
            db.query(NewsletterSubscription)
            .order_by(NewsletterSubscription.created_at.desc())
            .limit(200)
            .all()
        )
        db.query(NewsletterSubscription).filter(NewsletterSubscription.is_seen.is_(False)).update(
            {NewsletterSubscription.is_seen: True},
            synchronize_session=False,
        )
        db.commit()
        subscribers_error = None
    except SQLAlchemyError:
        db.rollback()
        subscriptions = []
        subscribers_error = "Database tables missing. Run contact_newsletter_tables.sql first."

    context.update(
        {
            "subscriptions": subscriptions,
            "error": subscribers_error,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_subscribers.html", context)


@router.get("/admin/admissions", response_class=HTMLResponse)
def admin_admissions_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admin Admissions")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    try:
        applications = (
            db.query(AdmissionApplication)
            .order_by(AdmissionApplication.created_at.desc(), AdmissionApplication.id.desc())
            .limit(200)
            .all()
        )
        db.query(AdmissionApplication).filter(AdmissionApplication.is_seen.is_(False)).update(
            {AdmissionApplication.is_seen: True},
            synchronize_session=False,
        )
        db.commit()
        admissions_error = None
    except SQLAlchemyError:
        db.rollback()
        applications = []
        admissions_error = "Database tables missing. Run admission_tables.sql first."

    context.update(
        {
            "applications": applications,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error") or admissions_error,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_admissions.html", context)


@router.get("/admin/admissions/{admission_id}", response_class=HTMLResponse)
def admin_admission_detail(admission_id: int, request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admission Details")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = (
        db.query(AdmissionApplication)
        .options(selectinload(AdmissionApplication.contacts), selectinload(AdmissionApplication.review))
        .filter(AdmissionApplication.id == admission_id)
        .first()
    )
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    if not application.is_seen:
        application.is_seen = True
        db.add(application)
        db.commit()

    payment_settings = _get_admission_payment_settings(db)
    whatsapp_chat_url = None
    if application.contacts:
        primary_phone = sorted(application.contacts, key=lambda c: c.sort_order)[0].contact_value
        body = build_whatsapp_message_body(application, payment_settings)
        whatsapp_chat_url = whatsapp_me_url_from_phone(primary_phone, text=body)

    context.update(
        {
            "application": application,
            "review": application.review,
            "admission_options": load_admission_options(db),
            "whatsapp_chat_url": whatsapp_chat_url,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_admission_detail.html", context)


@router.post("/admin/admissions/{admission_id}/send-followup-email")
def admin_send_admission_followup_email(
    admission_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = (
        db.query(AdmissionApplication)
        .options(selectinload(AdmissionApplication.review))
        .filter(AdmissionApplication.id == admission_id)
        .first()
    )
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    to_email, email_err = normalize_admission_email(application.email or "", required=True)
    if email_err or not to_email:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error={quote_plus('Save a valid email address on this application before sending.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    payment_settings = _get_admission_payment_settings(db)
    subject, plain, html_body = build_admission_followup_email(application, payment_settings)
    ok, send_err = send_multipart_email(to_email, subject, plain, html_body)
    if not ok:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error={quote_plus(send_err or 'Email could not be sent.')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/admin/admissions/{admission_id}?message={quote_plus('Email sent to the applicant.')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admissions/{admission_id}/application")
def admin_save_admission_application(
    admission_id: int,
    request: Request,
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
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = (
        db.query(AdmissionApplication)
        .options(selectinload(AdmissionApplication.contacts))
        .filter(AdmissionApplication.id == admission_id)
        .first()
    )
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    normalized_first_name = (first_name or "").strip()
    normalized_last_name = (last_name or "").strip()
    normalized_gender = (gender or "").strip()
    normalized_city = (city or "").strip()
    contact_values = [
        value.strip()
        for value in (contact_1, contact_2, contact_3, contact_4)
        if value and value.strip()
    ]

    def redirect_error(msg: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error={quote_plus(msg)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not normalized_first_name or not normalized_last_name:
        return redirect_error("Please fill first name and last name.")
    if not normalized_gender or not (date_of_birth or "").strip():
        return redirect_error("Please fill gender and date of birth.")
    normalized_email, email_err = normalize_admission_email(email, required=True)
    if email_err:
        return redirect_error(email_err)
    if not contact_values:
        return redirect_error("Please add at least one contact number.")
    if not normalized_city:
        return redirect_error("Please fill city.")

    try:
        parsed_date_of_birth = _optional_date_from_form(date_of_birth)
    except ValueError:
        return redirect_error("Please enter a valid date of birth.")
    if parsed_date_of_birth is None:
        return redirect_error("Please enter a valid date of birth.")

    old_photo_key = application.passport_photo_key
    pending_new_key: str | None = None
    pending_new_url: str | None = None
    if passport_photo and passport_photo.filename:
        try:
            pending_new_key, _, pending_new_url = upload_passport_photo_and_get_url(passport_photo, get_s3_config())
        except UploadValidationError as exc:
            return redirect_error(str(exc))
        except UploadServiceError as exc:
            return redirect_error(str(exc))

    application.first_name = normalized_first_name
    application.last_name = normalized_last_name
    application.gender = normalized_gender
    application.date_of_birth = parsed_date_of_birth
    application.email = normalized_email
    application.guardian_name = (guardian_name or "").strip() or None
    application.guardian_relation = (guardian_relation or "").strip() or None
    application.guardian_occupation = (guardian_occupation or "").strip() or None
    application.address_line = (address_line or "").strip() or None
    application.city = normalized_city
    application.state = (state_value or "").strip() or None
    application.pin_code = (pin_code or "").strip() or None
    application.special_remarks = (special_remarks or "").strip() or None
    application.discipline = (discipline or "").strip() or None
    application.grade = (grade or "").strip() or None
    application.affiliated = (affiliated or "").strip() or None
    application.preferred_teacher = (preferred_teacher or "").strip() or None
    application.is_seen = True

    if pending_new_key and pending_new_url:
        application.passport_photo_key = pending_new_key
        application.passport_photo_url = pending_new_url

    application.contacts.clear()
    for index, contact_value in enumerate(contact_values, start=1):
        application.contacts.append(
            AdmissionContact(contact_value=contact_value, sort_order=index)
        )

    try:
        db.add(application)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if pending_new_key:
            try:
                delete_image_by_key(pending_new_key, get_s3_config())
            except (UploadValidationError, UploadServiceError):
                pass
        return redirect_error("Could not save application details.")

    if pending_new_key and old_photo_key and old_photo_key != pending_new_key:
        try:
            delete_image_by_key(old_photo_key, get_s3_config())
        except (UploadValidationError, UploadServiceError):
            pass

    return RedirectResponse(
        url=f"/admin/admissions/{admission_id}?message=Application+details+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/admin/admissions/{admission_id}/download")
def admin_download_admission(admission_id: int, request: Request, db: Session = Depends(get_db)):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = (
        db.query(AdmissionApplication)
        .options(selectinload(AdmissionApplication.contacts), selectinload(AdmissionApplication.review))
        .filter(AdmissionApplication.id == admission_id)
        .first()
    )
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    filename_name = _download_filename_part(f"{application.first_name}-{application.last_name}")
    filename = f"musika-admission-{application.id}-{filename_name or 'application'}.pdf"
    payment_settings = _get_admission_payment_settings(db)
    return Response(
        content=build_admission_application_pdf(application, payment_settings=payment_settings),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/admissions/{admission_id}/delete")
def admin_delete_admission_application(
    admission_id: int,
    request: Request,
    delete_confirmation: str = Form(default=""),
    delete_return: str = Form(default="list"),
    db: Session = Depends(get_db),
):
    """Remove application row (cascade: contacts, office review) and delete passport photo from S3."""
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = db.query(AdmissionApplication).filter(AdmissionApplication.id == admission_id).first()
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if (delete_confirmation or "").strip().lower() != "delete":
        err = quote_plus("Type delete to confirm.")
        if (delete_return or "").strip().lower() == "detail":
            return RedirectResponse(
                url=f"/admin/admissions/{admission_id}?error={err}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/admissions?error={err}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    photo_key = application.passport_photo_key or extract_s3_object_key_from_url(application.passport_photo_url)

    try:
        db.delete(application)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            url="/admin/admissions?error=Could+not+delete+application",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if photo_key:
        try:
            delete_image_by_key(photo_key, get_s3_config())
        except (UploadValidationError, UploadServiceError):
            pass

    return RedirectResponse(
        url="/admin/admissions?message=Admission+application+deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/admin/admission-options", response_class=HTMLResponse)
def admin_admission_options_page(request: Request, db: Session = Depends(get_db)):
    context = shared_auth_context(request, "Admission Setup")
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    try:
        disciplines = (
            db.query(AdmissionDiscipline)
            .options(selectinload(AdmissionDiscipline.grades), selectinload(AdmissionDiscipline.teachers))
            .filter(AdmissionDiscipline.is_active.is_(True))
            .order_by(AdmissionDiscipline.name.asc())
            .all()
        )
        options_error = None
    except SQLAlchemyError:
        disciplines = []
        options_error = "Admission option tables missing. Create admission_disciplines, admission_grades, and admission_teachers first."

    payment_settings, payment_settings_error = _get_or_create_admission_payment_settings(db)

    context.update(
        {
            "disciplines": disciplines,
            "payment_settings": payment_settings,
            "payment_settings_error": payment_settings_error,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error") or options_error,
        }
    )
    _inject_admin_inbox_counts(context, db)
    return templates.TemplateResponse(request, "admin_admission_options.html", context)


@router.post("/admin/admission-options/payment-settings")
def admin_save_admission_payment_settings(
    request: Request,
    account_holder_name: str = Form(default=""),
    bank_account_number: str = Form(default=""),
    bank_ifsc: str = Form(default=""),
    upi_id: str = Form(default=""),
    scanner_image: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    def redirect_err(msg: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"/admin/admission-options?error={quote_plus(msg)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    row = db.query(AdmissionPaymentSettings).filter(AdmissionPaymentSettings.id == 1).first()
    if row is None:
        row = AdmissionPaymentSettings(id=1)
        db.add(row)

    prev_key = row.scanner_image_key

    row.account_holder_name = (account_holder_name or "").strip() or None
    row.bank_account_number = (bank_account_number or "").strip() or None
    ifsc = (bank_ifsc or "").strip().upper() or None
    row.bank_ifsc = ifsc
    row.upi_id = (upi_id or "").strip() or None

    if scanner_image and scanner_image.filename:
        try:
            new_key, _, public_url = upload_image_and_get_url(scanner_image, get_s3_config())
        except UploadValidationError as exc:
            return redirect_err(str(exc))
        except UploadServiceError as exc:
            return redirect_err(str(exc))
        if prev_key and prev_key != new_key:
            try:
                delete_image_by_key(prev_key, get_s3_config())
            except (UploadValidationError, UploadServiceError):
                pass
        row.scanner_image_key = new_key
        row.scanner_image_url = public_url

    try:
        db.add(row)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return redirect_err("Could not save payment settings. Run admission_tables.sql if admission_payment_settings is missing.")

    return RedirectResponse(
        url="/admin/admission-options?message=Payment+details+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/disciplines")
def admin_create_admission_discipline(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    normalized_name = (name or "").strip()
    if not normalized_name:
        return RedirectResponse(
            url="/admin/admission-options?error=Discipline+name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    existing = db.query(AdmissionDiscipline).filter(AdmissionDiscipline.name == normalized_name).first()
    if existing:
        existing.is_active = True
        db.add(existing)
    else:
        db.add(AdmissionDiscipline(name=normalized_name, is_active=True))
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Discipline+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/grades")
def admin_create_admission_grade(
    request: Request,
    discipline_id: int = Form(...),
    name: str = Form(...),
    sort_order: int = Form(default=0),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    discipline = (
        db.query(AdmissionDiscipline)
        .filter(AdmissionDiscipline.id == discipline_id, AdmissionDiscipline.is_active.is_(True))
        .first()
    )
    normalized_name = (name or "").strip()
    if not discipline or not normalized_name:
        return RedirectResponse(
            url="/admin/admission-options?error=Select+a+discipline+and+grade+name",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.add(
        AdmissionGrade(
            discipline_id=discipline.id,
            name=normalized_name,
            sort_order=sort_order,
            is_active=True,
        )
    )
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Grade+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/teachers")
def admin_create_admission_teacher(
    request: Request,
    discipline_id: int = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    discipline = (
        db.query(AdmissionDiscipline)
        .filter(AdmissionDiscipline.id == discipline_id, AdmissionDiscipline.is_active.is_(True))
        .first()
    )
    normalized_name = (name or "").strip()
    if not discipline or not normalized_name:
        return RedirectResponse(
            url="/admin/admission-options?error=Select+a+discipline+and+teacher+name",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.add(AdmissionTeacher(discipline_id=discipline.id, name=normalized_name, is_active=True))
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Teacher+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/disciplines/{discipline_id}/delete")
def admin_delete_admission_discipline(
    discipline_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    discipline = db.query(AdmissionDiscipline).filter(AdmissionDiscipline.id == discipline_id).first()
    if not discipline:
        return RedirectResponse(
            url="/admin/admission-options?error=Discipline+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.delete(discipline)
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Discipline+deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/grades/{grade_id}/delete")
def admin_delete_admission_grade(
    grade_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    grade = db.query(AdmissionGrade).filter(AdmissionGrade.id == grade_id).first()
    if not grade:
        return RedirectResponse(
            url="/admin/admission-options?error=Grade+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.delete(grade)
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Grade+deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admission-options/teachers/{teacher_id}/delete")
def admin_delete_admission_teacher(
    teacher_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    teacher = db.query(AdmissionTeacher).filter(AdmissionTeacher.id == teacher_id).first()
    if not teacher:
        return RedirectResponse(
            url="/admin/admission-options?error=Teacher+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.delete(teacher)
    db.commit()
    return RedirectResponse(
        url="/admin/admission-options?message=Teacher+deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/admissions/{admission_id}/review")
def admin_save_admission_review(
    admission_id: int,
    request: Request,
    accepted: str = Form(default=""),
    status_value: str = Form(default=""),
    fees_amount_inr: str = Form(default=""),
    invoice_no: str = Form(default=""),
    invoice_dated: str = Form(default=""),
    payment_method: str = Form(default=""),
    course_start_date: str = Form(default=""),
    course_duration: str = Form(default=""),
    class_type: str = Form(default=""),
    remarks: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    application = db.query(AdmissionApplication).filter(AdmissionApplication.id == admission_id).first()
    if not application:
        return RedirectResponse(
            url="/admin/admissions?error=Admission+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    normalized_status = (status_value or "").strip().lower() or application.status
    if normalized_status not in {"new", "reviewing", "accepted", "rejected", "waitlisted"}:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error=Invalid+admission+status",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    accepted_value: bool | None
    if accepted == "yes":
        accepted_value = True
    elif accepted == "no":
        accepted_value = False
    else:
        accepted_value = None

    try:
        parsed_invoice_date = _optional_date_from_form(invoice_dated)
        parsed_course_start_date = _optional_date_from_form(course_start_date)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error=Please+enter+valid+dates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    normalized_fees = (fees_amount_inr or "").strip()
    try:
        parsed_fees_amount = Decimal(normalized_fees) if normalized_fees else None
    except InvalidOperation:
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error=Please+enter+a+valid+fees+amount",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    review = application.review or AdmissionAdminReview(admission_id=application.id)
    review.reviewed_by_user_id = _current_admin_user_id(request)
    review.accepted = accepted_value
    review.fees_amount_inr = parsed_fees_amount
    review.invoice_no = (invoice_no or "").strip() or None
    review.invoice_dated = parsed_invoice_date
    review.payment_method = (payment_method or "").strip() or None
    review.course_start_date = parsed_course_start_date
    review.course_duration = (course_duration or "").strip() or None
    review.class_type = (class_type or "").strip() or None
    review.remarks = (remarks or "").strip() or None
    application.status = normalized_status
    application.is_seen = True

    try:
        db.add(application)
        db.add(review)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/admissions/{admission_id}?error=Could+not+save+review",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        url=f"/admin/admissions/{admission_id}?message=Admission+review+saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/dashboard/events")
def admin_create_event(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    location: str = Form(default=""),
    state: str = Form(default=""),
    event_date: str = Form(...),
    event_time: str = Form(...),
    image_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    normalized_title = (title or "").strip()
    if not normalized_title:
        return RedirectResponse(
            url="/admin/events?error=Event+title+is+required", status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        parsed_date = dt_date.fromisoformat((event_date or "").strip())
    except ValueError:
        return RedirectResponse(
            url="/admin/events?error=Invalid+event+date", status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        parsed_time = dt_time.fromisoformat((event_time or "").strip())
    except ValueError:
        return RedirectResponse(
            url="/admin/events?error=Invalid+event+time", status_code=status.HTTP_303_SEE_OTHER
        )

    event = Event(
        title=normalized_title,
        description=(description or "").strip() or None,
        location=(location or "").strip() or None,
        state=(state or "").strip() or None,
        event_date=parsed_date,
        event_time=parsed_time,
    )
    db.add(event)
    db.flush()

    s3_config = get_s3_config()
    uploaded_images: list[EventImage] = []
    for image_file in image_files:
        if not image_file or not image_file.filename:
            continue
        try:
            _, _, public_image_url = upload_image_and_get_url(image_file, s3_config)
        except UploadValidationError as exc:
            db.rollback()
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            db.rollback()
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        uploaded_images.append(EventImage(event_id=event.id, image_url=public_image_url))

    if uploaded_images:
        db.add_all(uploaded_images)

    db.commit()
    return RedirectResponse(
        url="/admin/events?message=Event+created+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/events/{event_id}/update")
def admin_update_event(
    event_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    location: str = Form(default=""),
    state: str = Form(default=""),
    event_date: str = Form(...),
    event_time: str = Form(...),
    image_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return RedirectResponse(
            url="/admin/events?error=Event+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    normalized_title = (title or "").strip()
    if not normalized_title:
        return RedirectResponse(
            url="/admin/events?error=Event+title+is+required", status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        parsed_date = dt_date.fromisoformat((event_date or "").strip())
    except ValueError:
        return RedirectResponse(
            url="/admin/events?error=Invalid+event+date", status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        parsed_time = dt_time.fromisoformat((event_time or "").strip())
    except ValueError:
        return RedirectResponse(
            url="/admin/events?error=Invalid+event+time", status_code=status.HTTP_303_SEE_OTHER
        )

    event.title = normalized_title
    event.description = (description or "").strip() or None
    event.location = (location or "").strip() or None
    event.state = (state or "").strip() or None
    event.event_date = parsed_date
    event.event_time = parsed_time

    s3_config = get_s3_config()
    uploaded_images: list[EventImage] = []
    for image_file in image_files:
        if not image_file or not image_file.filename:
            continue
        try:
            _, _, public_image_url = upload_image_and_get_url(image_file, s3_config)
        except UploadValidationError as exc:
            db.rollback()
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            db.rollback()
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        uploaded_images.append(EventImage(event_id=event.id, image_url=public_image_url))

    if uploaded_images:
        db.add_all(uploaded_images)

    db.commit()
    return RedirectResponse(
        url="/admin/events?message=Event+updated+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/events/{event_id}/images/{image_id}/delete")
def admin_delete_event_image(
    event_id: int,
    image_id: int,
    request: Request,
    delete_confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    image = (
        db.query(EventImage)
        .filter(EventImage.id == image_id, EventImage.event_id == event_id)
        .first()
    )
    if not image:
        return RedirectResponse(
            url="/admin/events?error=Event+image+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    confirm_mode = (request.query_params.get("confirm_mode") or "").strip().lower()
    if confirm_mode == "typed":
        normalized_confirmation = (delete_confirmation or "").strip().lower()
        if not normalized_confirmation.startswith("delete"):
            return RedirectResponse(
                url="/admin/events?error=Type+delete+to+confirm+image+deletion",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    image_key = extract_s3_object_key_from_url(image.image_url)
    if image_key:
        try:
            delete_image_by_key(image_key, get_s3_config())
        except UploadValidationError as exc:
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    db.delete(image)
    db.commit()
    return RedirectResponse(
        url="/admin/events?message=Event+image+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/dashboard/events/{event_id}/delete")
def admin_delete_event(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    event = db.query(Event).options(selectinload(Event.images)).filter(Event.id == event_id).first()
    if not event:
        return RedirectResponse(url="/admin/events?error=Event+not+found", status_code=status.HTTP_303_SEE_OTHER)

    for image in event.images:
        image_key = extract_s3_object_key_from_url(image.image_url)
        if not image_key:
            continue
        try:
            delete_image_by_key(image_key, get_s3_config())
        except UploadValidationError as exc:
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            return RedirectResponse(
                url=f"/admin/events?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    db.delete(event)
    db.commit()
    return RedirectResponse(
        url="/admin/events?message=Event+deleted+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/artists")
def admin_create_artist(
    request: Request,
    name: str = Form(...),
    title: str = Form(default=""),
    bio: str = Form(default=""),
    hero_image_file: UploadFile | None = File(default=None),
    facebook_url: str = Form(default=""),
    instagram_url: str = Form(default=""),
    twitter_url: str = Form(default=""),
    whatsapp_url: str = Form(default=""),
    email: str = Form(default=""),
    youtube_url: str = Form(default=""),
    spotify_url: str = Form(default=""),
    youtube_music_url: str = Form(default=""),
    amazon_music_url: str = Form(default=""),
    imusic_url: str = Form(default=""),
    featured_media_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    normalized_name = (name or "").strip()
    if not normalized_name:
        return RedirectResponse(
            url="/admin/artist?error=Artist+name+is+required", status_code=status.HTTP_303_SEE_OTHER
        )

    hero_image_url: str | None = None
    if hero_image_file and hero_image_file.filename:
        try:
            _, _, hero_image_url = upload_image_and_get_url(hero_image_file, get_s3_config())
        except UploadValidationError as exc:
            return RedirectResponse(
                url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            return RedirectResponse(
                url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    has_featured_input = bool(featured_media_file and featured_media_file.filename)
    resolved_featured_url: str | None = None
    if has_featured_input:
        if featured_media_file and featured_media_file.filename:
            try:
                _, _, uploaded_featured_url = upload_image_and_get_url(featured_media_file, get_s3_config())
            except UploadValidationError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            except UploadServiceError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            resolved_featured_url = uploaded_featured_url

    artist = Artist(
        name=normalized_name,
        title=(title or "").strip() or None,
        bio=(bio or "").strip() or None,
        hero_image_url=hero_image_url,
        facebook_url=(facebook_url or "").strip() or None,
        instagram_url=(instagram_url or "").strip() or None,
        twitter_url=(twitter_url or "").strip() or None,
        whatsapp_url=normalize_whatsapp_input(whatsapp_url),
        email=(email or "").strip() or None,
        youtube_url=(youtube_url or "").strip() or None,
        spotify_url=(spotify_url or "").strip() or None,
        youtube_music_url=(youtube_music_url or "").strip() or None,
        amazon_music_url=(amazon_music_url or "").strip() or None,
        imusic_url=(imusic_url or "").strip() or None,
        featured_media_type=("image" if resolved_featured_url else None),
        featured_media_url=resolved_featured_url,
        featured_media_thumbnail_url=None,
    )
    db.add(artist)
    db.commit()
    return RedirectResponse(
        url="/admin/artist?message=Artist+created+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/artists/media")
def admin_add_artist_media(
    request: Request,
    artist_id: int = Form(...),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        return RedirectResponse(
            url="/admin/artist?error=Artist+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    normalized_type = "image"

    if not file or not file.filename:
        return RedirectResponse(
            url="/admin/artist?error=Image+file+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        _, _, resolved_media_url = upload_image_and_get_url(file, get_s3_config())
    except UploadValidationError as exc:
        return RedirectResponse(
            url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        return RedirectResponse(
            url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    media = Media(
        artist_id=artist.id,
        media_type=normalized_type,
        media_url=resolved_media_url,
        thumbnail_url=None,
    )
    db.add(media)
    db.commit()
    return RedirectResponse(
        url="/admin/artist?message=Media+added+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/artists/{artist_id}/delete")
def admin_delete_artist(
    artist_id: int,
    request: Request,
    delete_confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        return RedirectResponse(
            url="/admin/artist?error=Artist+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    confirm_mode = (request.query_params.get("confirm_mode") or "").strip().lower()
    if confirm_mode == "typed":
        normalized_confirmation = (delete_confirmation or "").strip().lower()
        expected_confirmation = f"delete {artist.name}".strip().lower()
        if normalized_confirmation != expected_confirmation:
            return RedirectResponse(
                url="/admin/artist?error=Delete+confirmation+did+not+match.+Use+delete+" + artist.name.replace(" ", "+"),
                status_code=status.HTTP_303_SEE_OTHER,
            )

    db.delete(artist)
    db.commit()
    return RedirectResponse(
        url="/admin/artist?message=Artist+deleted+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/artists/{artist_id}/update")
def admin_update_artist(
    artist_id: int,
    request: Request,
    name: str = Form(...),
    title: str = Form(default=""),
    bio: str = Form(default=""),
    hero_image_file: UploadFile | None = File(default=None),
    facebook_url: str = Form(default=""),
    instagram_url: str = Form(default=""),
    twitter_url: str = Form(default=""),
    whatsapp_url: str = Form(default=""),
    email: str = Form(default=""),
    youtube_url: str = Form(default=""),
    spotify_url: str = Form(default=""),
    youtube_music_url: str = Form(default=""),
    amazon_music_url: str = Form(default=""),
    imusic_url: str = Form(default=""),
    featured_media_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        return RedirectResponse(
            url="/admin/artist?error=Artist+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    normalized_name = (name or "").strip()
    if not normalized_name:
        return RedirectResponse(
            url="/admin/artist?error=Artist+name+is+required", status_code=status.HTTP_303_SEE_OTHER
        )

    artist.name = normalized_name
    artist.title = (title or "").strip() or None
    artist.bio = (bio or "").strip() or None
    artist.facebook_url = (facebook_url or "").strip() or None
    artist.instagram_url = (instagram_url or "").strip() or None
    artist.twitter_url = (twitter_url or "").strip() or None
    artist.whatsapp_url = normalize_whatsapp_input(whatsapp_url)
    artist.email = (email or "").strip() or None
    artist.youtube_url = (youtube_url or "").strip() or None
    artist.spotify_url = (spotify_url or "").strip() or None
    artist.youtube_music_url = (youtube_music_url or "").strip() or None
    artist.amazon_music_url = (amazon_music_url or "").strip() or None
    artist.imusic_url = (imusic_url or "").strip() or None
    s3_config = get_s3_config()

    if hero_image_file and hero_image_file.filename:
        previous_hero_image_url = artist.hero_image_url
        try:
            _, _, public_image_url = upload_image_and_get_url(hero_image_file, s3_config)
        except UploadValidationError as exc:
            return RedirectResponse(
                url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except UploadServiceError as exc:
            return RedirectResponse(
                url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        previous_hero_key = extract_s3_object_key_from_url(previous_hero_image_url)
        if previous_hero_key:
            try:
                delete_image_by_key(previous_hero_key, s3_config)
            except UploadValidationError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            except UploadServiceError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
        artist.hero_image_url = public_image_url

    has_featured_input = bool(featured_media_file and featured_media_file.filename)
    if has_featured_input:
        resolved_featured_url = ""
        if featured_media_file and featured_media_file.filename:
            previous_featured_image_url = artist.featured_media_url
            try:
                _, _, uploaded_featured_url = upload_image_and_get_url(featured_media_file, s3_config)
            except UploadValidationError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            except UploadServiceError as exc:
                return RedirectResponse(
                    url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            previous_featured_key = extract_s3_object_key_from_url(previous_featured_image_url)
            if previous_featured_key:
                try:
                    delete_image_by_key(previous_featured_key, s3_config)
                except UploadValidationError as exc:
                    return RedirectResponse(
                        url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                except UploadServiceError as exc:
                    return RedirectResponse(
                        url=f"/admin/artist?error={str(exc).replace(' ', '+')}",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
            resolved_featured_url = uploaded_featured_url

        artist.featured_media_type = "image"
        artist.featured_media_url = resolved_featured_url
        artist.featured_media_thumbnail_url = None
    db.commit()
    return RedirectResponse(
        url="/admin/artist?message=Artist+updated+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/dashboard/artists/media/{media_id}/delete")
def admin_delete_artist_media(
    media_id: int,
    request: Request,
    delete_confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_redirect = require_admin(request)
    if admin_redirect:
        return admin_redirect

    return_to = request.query_params.get("return_to")
    confirm_mode = (request.query_params.get("confirm_mode") or "").strip().lower()
    target_url = return_to or "/admin/artist"

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error=Media+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if confirm_mode == "typed":
        normalized_confirmation = (delete_confirmation or "").strip().lower()
        if not normalized_confirmation.startswith("delete"):
            separator = "&" if "?" in target_url else "?"
            return RedirectResponse(
                url=f"{target_url}{separator}error=Type+delete+to+confirm+deletion",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    db.delete(media)
    db.commit()
    separator = "&" if "?" in target_url else "?"
    return RedirectResponse(
        url=f"{target_url}{separator}message=Media+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
