import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "replace_with_long_random_secret")
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", "720"))


def hash_password(password: str) -> bytes:
    return pwd_context.hash(password).encode("utf-8")


def verify_password(plain_password: str, hashed_password_bytes: bytes) -> bool:
    hashed_password = hashed_password_bytes.decode("utf-8")
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], minutes: int | None = None) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=minutes or JWT_EXP_MINUTES)
    payload = {**data, "exp": expire_at}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
