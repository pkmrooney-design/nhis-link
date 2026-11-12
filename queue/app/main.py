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

@app.get("/board")
def board_page(request: Request):
    url = netinfo.public_base_url(str(request.base_url), request.url.hostname or "", request.url.port)
    return templates.TemplateResponse(request, "board.html", {"join_url": url})


@app.get("/api/board")
def api_board():
    return services.get_board_state()


@app.get("/qr.png")
def qr_png(request: Request):
    url = netinfo.public_base_url(str(request.base_url), request.url.hostname or "", request.url.port)
    img = qrcode.make(url, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.get("/events")
async def events(request: Request):
    async def stream():
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            changed = await broadcaster.wait(15)
            yield "event: change\ndata: 1\n\n" if changed else ": ping\n\n"

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


@app.post("/admin/login")
async def admin_login(payload: dict = Body(...)):
    if not auth.check_password(str(payload.get("password", ""))):
        await asyncio.sleep(1)  # 무차별 대입 속도 늦추기
        return JSONResponse({"detail": "비밀번호가 올바르지 않습니다"}, status_code=401)
    value, _ = auth.new_session_cookie()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.COOKIE, value, max_age=auth.MAX_AGE, httponly=True, samesite="strict", path="/admin"
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
