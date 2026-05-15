import re

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_s3_config, normalize_stored_asset_url
from app.db import get_db
from app.models import GalleryGenre, GalleryImage
from app.routers.auth import AUTH_COOKIE_NAME
from app.security import decode_access_token
from app.services.s3_upload import UploadServiceError, UploadValidationError, upload_image_and_get_url

router = APIRouter()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def require_admin(request: Request) -> dict:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required.")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token.") from exc
    if not payload.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return payload


@router.post("/admin/gallery/genres", status_code=status.HTTP_201_CREATED)
def create_gallery_genre(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Genre name is required.")
    slug = slugify(normalized_name)
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid genre name.")

    existing = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Genre already exists.")

    genre = GalleryGenre(name=normalized_name, slug=slug)
    db.add(genre)
    db.commit()
    db.refresh(genre)
    return {"id": genre.id, "name": genre.name, "slug": genre.slug, "created_at": genre.created_at.isoformat()}


@router.get("/gallery/genres")
def list_gallery_genres(db: Session = Depends(get_db)):
    genres = db.query(GalleryGenre).order_by(GalleryGenre.name.asc()).all()
    return [
        {"id": genre.id, "name": genre.name, "slug": genre.slug, "created_at": genre.created_at.isoformat()}
        for genre in genres
    ]


@router.post("/admin/gallery/images", status_code=status.HTTP_201_CREATED)
def upload_gallery_image(
    request: Request,
    genre_slug: str = Form(...),
    caption: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    slug = slugify(genre_slug)
    genre = db.query(GalleryGenre).filter(GalleryGenre.slug == slug).first()
    if not genre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Genre not found.")

    try:
        object_key, _, public_image_url = upload_image_and_get_url(file, get_s3_config())
    except UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UploadServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    image = GalleryImage(
        genre_id=genre.id,
        s3_key=object_key,
        image_url=public_image_url,
        caption=(caption or "").strip() or None,
        is_active=True,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return {
        "id": image.id,
        "genre": genre.slug,
        "image_url": normalize_stored_asset_url(image.image_url),
        "caption": image.caption,
        "created_at": image.created_at.isoformat(),
    }


@router.get("/gallery/images")
def list_gallery_images(
    genre: str | None = Query(default=None),
    limit: int = Query(default=9, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = (
        db.query(GalleryImage, GalleryGenre.slug)
        .join(GalleryGenre, GalleryGenre.id == GalleryImage.genre_id)
        .filter(GalleryImage.is_active.is_(True))
    )
    if genre:
        query = query.filter(GalleryGenre.slug == slugify(genre))

    total = query.count()
    rows = query.order_by(GalleryImage.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        {
            "id": image.id,
            "genre": genre_slug,
            "image_url": normalize_stored_asset_url(image.image_url),
            "caption": image.caption,
            "created_at": image.created_at.isoformat(),
        }
        for image, genre_slug in rows
    ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }
