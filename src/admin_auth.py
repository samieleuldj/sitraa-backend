import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("ADMIN_TOKEN_HOURS", "12"))

security = HTTPBearer(auto_error=False)


def get_admin_credentials() -> tuple[str, str]:
    username = (os.getenv("ADMIN_USERNAME") or "").strip()
    password = (os.getenv("ADMIN_PASSWORD") or "").strip()
    return username, password


def get_jwt_secret() -> str:
    secret = (os.getenv("SECRET_KEY") or os.getenv("ADMIN_JWT_SECRET") or "").strip()
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="SECRET_KEY is not configured on the server",
        )
    return secret


def create_admin_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_HOURS)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=ALGORITHM)


def verify_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            get_jwt_secret(),
            algorithms=[ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return str(payload.get("sub") or "")


def authenticate_admin(username: str, password: str) -> str | None:
    expected_user, expected_pass = get_admin_credentials()
    if not expected_user or not expected_pass:
        return None
    if username == expected_user and password == expected_pass:
        return create_admin_token(username)
    return None
