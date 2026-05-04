import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.content import (
    BRAND_LOGO_URL,
    FOOTER_CREDIT_LOGO_URL,
    FOOTER_CREDIT_URL,
    FOOTER_FACEBOOK_URL,
    FOOTER_INSTAGRAM_URL,
    FOOTER_YOUTUBE_URL,
)
from app.db import get_db
from app.models import User
from app.security import create_access_token, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")

AUTH_COOKIE_NAME = "musika_auth"


def shared_auth_context(request: Request, title: str):
    return {
        "request": request,
        "site_name": "MUSIKA",
        "brand_logo_url": BRAND_LOGO_URL,
        "footer_credit_logo_url": FOOTER_CREDIT_LOGO_URL,
        "footer_credit_url": FOOTER_CREDIT_URL,
        "footer_facebook_url": FOOTER_FACEBOOK_URL,
        "footer_instagram_url": FOOTER_INSTAGRAM_URL,
        "footer_youtube_url": FOOTER_YOUTUBE_URL,
        "nav_items": [],
        "active_path": request.url.path,
        "title": title,
        "error": None,
        "message": None,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", shared_auth_context(request, "User Login"))


@router.post("/login", response_class=HTMLResponse)
def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "User Login")
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not user.is_active or not verify_password(password, user.password_bytes):
        context["error"] = "Invalid email or password."
        return templates.TemplateResponse(
            request, "login.html", context, status_code=status.HTTP_401_UNAUTHORIZED
        )

    token = create_access_token({"sub": str(user.id), "email": user.email, "is_admin": user.is_admin})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request, "forgot_password.html", shared_auth_context(request, "Forgot Password")
    )


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    context = shared_auth_context(request, "Forgot Password")
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user and user.is_active:
        user.forgot_token = secrets.token_urlsafe(32)
        user.forgot_token_expires_at = datetime.utcnow() + timedelta(minutes=30)
        db.add(user)
        db.commit()
    context["message"] = "If this email exists, a password reset has been initiated."
    return templates.TemplateResponse(request, "forgot_password.html", context)


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response
