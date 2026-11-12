import secrets

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config

COOKIE = "admin_session"
MAX_AGE = 12 * 60 * 60  # 12시간

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="admin")


def check_password(password: str) -> bool:
    if not config.ADMIN_PASSWORD:
        return False
    return secrets.compare_digest(password.encode(), config.ADMIN_PASSWORD.encode())


def new_session_cookie() -> tuple[str, str]:
    """(쿠키 값, CSRF 토큰)"""
    csrf = secrets.token_urlsafe(16)
    return _serializer.dumps({"csrf": csrf}), csrf


def read_session(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        return _serializer.loads(raw, max_age=MAX_AGE)
    except BadSignature:
        return None


def require_admin_api(request: Request) -> dict:
    """관리자 API 용: 로그인 + CSRF 헤더 확인."""
    session = read_session(request)
    if session is None:
        raise HTTPException(401, "로그인이 필요합니다")
    if request.method != "GET":
        token = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(token, session["csrf"]):
            raise HTTPException(403, "잘못된 요청입니다")
    return session
