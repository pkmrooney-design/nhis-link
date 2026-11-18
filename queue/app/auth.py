import secrets
import time
from collections import deque

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config

COOKIE = "admin_session"
MAX_AGE = 12 * 60 * 60  # 12시간

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="admin")


# 인터넷에 공개했을 때 비밀번호 무차별 대입을 막기 위한 전체 실패 횟수 제한
FAIL_WINDOW_SEC = 10 * 60
MAX_FAILS = 10
_failures: deque[float] = deque()


def _prune(now: float) -> None:
    while _failures and now - _failures[0] > FAIL_WINDOW_SEC:
        _failures.popleft()


def login_locked() -> bool:
    _prune(time.monotonic())
    return len(_failures) >= MAX_FAILS


def record_failure() -> None:
    now = time.monotonic()
    _prune(now)
    _failures.append(now)


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
