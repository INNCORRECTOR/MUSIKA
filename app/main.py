import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import SessionLocal
from app.models import User
from app.routers.admin_routes import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.gallery_routes import router as gallery_router
from app.routers.pages import router as pages_router
from app.security import hash_password


def seed_default_admin() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@musika.local").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.email == admin_email).first()
        if existing_admin:
            return
        admin_user = User(
            email=admin_email,
            password_bytes=hash_password(admin_password),
            is_admin=True,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Database schema is managed outside app startup (manual SQL or migrations).
    seed_default_admin()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(gallery_router)
