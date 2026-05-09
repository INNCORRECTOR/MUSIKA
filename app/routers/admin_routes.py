from datetime import date as dt_date, time as dt_time
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload
import json

from app.config import get_s3_config
from app.db import get_db
from app.models import (
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
from app.routers.admin_common import extract_s3_object_key_from_url, normalize_whatsapp_input, require_admin
from app.routers.gallery_routes import slugify
from app.routers.auth import AUTH_COOKIE_NAME, shared_auth_context
from app.security import create_access_token, verify_password
from app.services.s3_upload import (
    UploadServiceError,
    UploadValidationError,
    delete_image_by_key,
    upload_image_and_get_url,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _ensure_inbox_seen_columns(db: Session) -> None:
    try:
        inspector = inspect(db.bind)
        contact_columns = {column["name"] for column in inspector.get_columns("contact_messages")}
        subscription_columns = {column["name"] for column in inspector.get_columns("newsletter_subscriptions")}
    except Exception:
        return

    has_changes = False
    if "is_seen" not in contact_columns:
        try:
            db.execute(text("ALTER TABLE contact_messages ADD COLUMN is_seen BOOLEAN NOT NULL DEFAULT 0"))
            has_changes = True
        except SQLAlchemyError:
            db.rollback()
    if "is_seen" not in subscription_columns:
        try:
            db.execute(text("ALTER TABLE newsletter_subscriptions ADD COLUMN is_seen BOOLEAN NOT NULL DEFAULT 0"))
            has_changes = True
        except SQLAlchemyError:
            db.rollback()

    if has_changes:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()


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
    except SQLAlchemyError:
        unread_contact_count = 0
        unread_subscription_count = 0

    context.update(
        {
            "unread_contact_count": unread_contact_count,
            "unread_subscription_count": unread_subscription_count,
            "unread_total_count": unread_contact_count + unread_subscription_count,
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
            url="/admin/gallary?error=Invalid+category+name", status_code=status.HTTP_303_SEE_OTHER
        )

    exists = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if exists:
        return RedirectResponse(
            url="/admin/gallary?error=Category+already+exists", status_code=status.HTTP_303_SEE_OTHER
        )

    genre = GalleryGenre(name=normalized_name, slug=slug)
    db.add(genre)
    db.commit()
    return RedirectResponse(
        url="/admin/gallary?message=Category+created+successfully", status_code=status.HTTP_303_SEE_OTHER
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
            url="/admin/gallary?error=Category+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        object_key, _, public_image_url = upload_image_and_get_url(file, get_s3_config())
    except UploadValidationError as exc:
        return RedirectResponse(
            url=f"/admin/gallary?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        return RedirectResponse(
            url=f"/admin/gallary?error={str(exc).replace(' ', '+')}",
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
        url="/admin/gallary?message=Image+uploaded+successfully", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/admin/gallary", response_class=HTMLResponse)
@router.get("/admin/gallery", response_class=HTMLResponse)
def admin_gallary_page(
    request: Request,
    page: int = 1,
    page_size: int = 5,
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Admin Gallary")
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
    return templates.TemplateResponse(request, "admingallary.html", context)


@router.get("/admin/gallary/categories/{genre_slug}", response_class=HTMLResponse)
@router.get("/admin/gallery/categories/{genre_slug}", response_class=HTMLResponse)
def admin_gallary_category_page(
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
            url="/admin/gallary?error=Category+not+found",
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
    return templates.TemplateResponse(request, "admingallary_category.html", context)


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
        target_url = return_to or "/admin/gallary"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error=Image+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        delete_image_by_key(image.s3_key, get_s3_config())
    except UploadValidationError as exc:
        target_url = return_to or "/admin/gallary"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        target_url = return_to or "/admin/gallary"
        separator = "&" if "?" in target_url else "?"
        return RedirectResponse(
            url=f"{target_url}{separator}error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.delete(image)
    db.commit()
    target_url = return_to or "/admin/gallary"
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
            url="/admin/gallary?error=Category+not+found", status_code=status.HTTP_303_SEE_OTHER
        )

    expected_confirmation = f"delete {genre.name}".strip().lower()
    provided_confirmation = (delete_confirmation or "").strip().lower()
    if provided_confirmation != expected_confirmation:
        return RedirectResponse(
            url="/admin/gallary?error=Delete+confirmation+did+not+match.+Use+delete+" + genre.name.replace(" ", "+"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    linked_images = db.query(GalleryImage).filter(GalleryImage.genre_id == genre.id).all()
    try:
        for image in linked_images:
            delete_image_by_key(image.s3_key, get_s3_config())
    except UploadValidationError as exc:
        return RedirectResponse(
            url=f"/admin/gallary?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadServiceError as exc:
        return RedirectResponse(
            url=f"/admin/gallary?error={str(exc).replace(' ', '+')}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.delete(genre)
    db.commit()
    return RedirectResponse(
        url="/admin/gallary?message=Category+deleted+successfully", status_code=status.HTTP_303_SEE_OTHER
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
