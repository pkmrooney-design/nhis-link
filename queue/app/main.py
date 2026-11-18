import asyncio
import io
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import qrcode
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, config, db, netinfo, services
from .events import broadcaster
from .models import ACTIVE_STATUSES

log = logging.getLogger("queue")
BASE = Path(__file__).parent
TOKEN_COOKIE = "qtoken"
PURGE_INTERVAL_SEC = 6 * 60 * 60
LOGIN_FAIL_DELAY_SEC = 1  # 비밀번호가 틀리면 응답을 늦춰 무차별 대입 속도를 늦춤


async def _purge_loop() -> None:
    while True:
        try:
            n = await asyncio.to_thread(services.purge_personal_data, config.RETENTION_DAYS)
            if n:
                log.info("보관 기간(%d일) 지난 접수 %d건의 개인정보 삭제", config.RETENTION_DAYS, n)
        except Exception:
            log.exception("개인정보 정리 실패")
        await asyncio.sleep(PURGE_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.create_all()
    broadcaster.bind(asyncio.get_running_loop())
    if not config.ADMIN_PASSWORD:
        log.warning("ADMIN_PASSWORD 가 설정되지 않아 관리자 로그인이 불가능합니다")
    task = asyncio.create_task(_purge_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["store_name"] = config.STORE_NAME
templates.env.globals["has_logo"] = (BASE / "static" / "logo.png").exists()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # 토큰이 든 URL 이 외부 사이트로 새지 않도록
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/api", "/admin", "/t/")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _set_token_cookie(response, token: str) -> None:
    response.set_cookie(
        TOKEN_COOKIE, token, max_age=24 * 60 * 60, httponly=True, samesite="lax"
    )


# ---------- 손님 화면 ----------

@app.get("/")
def index(request: Request):
    entry = services.get_entry_by_token(request.cookies.get(TOKEN_COOKIE, ""))
    if entry and entry.date == services.today() and entry.status in ACTIVE_STATUSES:
        return RedirectResponse(f"/t/{entry.token}", status_code=303)
    return templates.TemplateResponse(
        request, "index.html", {"state": services.get_public_state()}
    )


@app.get("/t/{token}")
def ticket_page(request: Request, token: str):
    if services.get_entry_by_token(token) is None:
        return templates.TemplateResponse(request, "not_found.html", status_code=404)
    response = templates.TemplateResponse(request, "ticket.html", {"token": token})
    _set_token_cookie(response, token)
    return response


@app.get("/api/queue")
def api_queue():
    return services.get_public_state()


@app.post("/api/tickets")
def api_issue(payload: dict = Body(...)):
    try:
        entry, created = services.issue_ticket(
            str(payload.get("name", "")), str(payload.get("phone", ""))
        )
    except services.ValidationError as e:
        return JSONResponse({"field": e.field, "detail": e.message}, status_code=422)
    except services.ClosedError:
        return JSONResponse({"detail": "현재 접수가 마감되었습니다"}, status_code=409)
    if created:
        broadcaster.notify()
    response = JSONResponse(
        {"token": entry.token, "url": f"/t/{entry.token}", "existing": not created},
        status_code=201 if created else 200,
    )
    _set_token_cookie(response, entry.token)
    return response


@app.get("/api/ticket/{token}")
def api_ticket(token: str):
    view = services.get_ticket_view(token)
    if view is None:
        raise HTTPException(404, "번호를 찾을 수 없습니다")
    return view


@app.post("/api/ticket/{token}/cancel")
def api_cancel(token: str):
    if not services.cancel_ticket(token):
        raise HTTPException(409, "취소할 수 없는 상태입니다")
    broadcaster.notify()
    response = JSONResponse({"ok": True})
    response.delete_cookie(TOKEN_COOKIE)
    return response


# ---------- 현황판 (TV) ----------

def _base_url(request: Request) -> str:
    """손님 휴대폰·TV 가 접속할 주소 (끝에 / 포함)."""
    return netinfo.public_base_url(str(request.base_url), request.url.hostname or "", request.url.port)


# QR코드로 만들 수 있는 화면 (임의 주소를 QR로 만들지 못하도록 고정)
QR_TARGETS = {"": "", "board": "board", "admin": "admin"}


@app.get("/board")
def board_page(request: Request):
    return templates.TemplateResponse(request, "board.html", {"join_url": _base_url(request)})


@app.get("/api/board")
def api_board():
    return services.get_board_state()


@app.get("/qr.png")
def qr_png(request: Request, to: str = ""):
    if to not in QR_TARGETS:
        raise HTTPException(404)
    url = _base_url(request) + QR_TARGETS[to]
    img = qrcode.make(url, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.get("/events")
async def events(request: Request):
    async def stream():
        # 화면은 ping/change 를 실제로 받아야 실시간 연결로 판단함
        # (중간 프록시가 스트림을 모아두면 받지 못해 5초 확인으로 전환)
        yield "retry: 3000\nevent: ping\ndata: 1\n\n"
        while not await request.is_disconnected():
            changed = await broadcaster.wait(15)
            yield "event: change\ndata: 1\n\n" if changed else "event: ping\ndata: 1\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 관리자 화면 ----------

@app.get("/admin")
def admin_page(request: Request):
    session = auth.read_session(request)
    if session is None:
        return templates.TemplateResponse(
            request, "login.html", {"configured": bool(config.ADMIN_PASSWORD)}
        )
    return templates.TemplateResponse(request, "admin.html", {"csrf": session["csrf"]})


@app.get("/admin/links")
def admin_links(request: Request):
    """손님·현황판·관리자 접속 주소와 QR코드를 한 장에 모아 보여주고 인쇄하는 화면."""
    if auth.read_session(request) is None:
        return RedirectResponse("/admin", status_code=303)
    base = _base_url(request)
    links = [
        {"key": "", "title": "손님 접수", "url": base,
         "desc": "매장 입구·카운터에 붙여두는 QR코드입니다. 손님이 찍어서 대기번호를 받습니다."},
        {"key": "board", "title": "현황판 (TV)", "url": base + "board",
         "desc": "TV나 모니터의 브라우저에서 엽니다. 호출 번호와 대기 목록이 나옵니다."},
        {"key": "admin", "title": "관리자", "url": base + "admin",
         "desc": "직원 휴대폰·태블릿에서 엽니다. 비밀번호로 로그인합니다. 손님에게 공개하지 마세요."},
    ]
    return templates.TemplateResponse(
        request, "links.html",
        {"links": links, "auto": not config.PUBLIC_URL, "ip": netinfo.lan_ip()},
    )


@app.post("/admin/login")
async def admin_login(request: Request, payload: dict = Body(...)):
    if auth.login_locked():
        return JSONResponse(
            {"detail": "로그인 실패가 너무 많아 잠시 막혔습니다. 10분 뒤 다시 시도해주세요"},
            status_code=429,
        )
    if not auth.check_password(str(payload.get("password", ""))):
        auth.record_failure()
        await asyncio.sleep(LOGIN_FAIL_DELAY_SEC)
        return JSONResponse({"detail": "비밀번호가 올바르지 않습니다"}, status_code=401)
    value, _ = auth.new_session_cookie()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.COOKIE, value, max_age=auth.MAX_AGE, httponly=True, samesite="strict", path="/admin",
        secure=request.url.scheme == "https",
    )
    return response


@app.post("/admin/logout")
def admin_logout(_=Depends(auth.require_admin_api)):
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE, path="/admin")
    return response


@app.get("/admin/api/state")
def admin_state(_=Depends(auth.require_admin_api)):
    return services.get_admin_state()


@app.post("/admin/api/entries/{entry_id}/{action}")
def admin_entry_action(entry_id: int, action: str, _=Depends(auth.require_admin_api)):
    if not services.admin_action(entry_id, action):
        raise HTTPException(409, "처리할 수 없는 상태입니다")
    broadcaster.notify()
    return {"ok": True}


@app.post("/admin/api/open")
def admin_set_open(payload: dict = Body(...), _=Depends(auth.require_admin_api)):
    services.set_open(bool(payload.get("open")))
    broadcaster.notify()
    return {"ok": True, "is_open": services.get_open()}
