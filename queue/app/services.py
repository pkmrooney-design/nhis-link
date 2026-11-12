"""접수·상태 변경·통계 등 핵심 로직. 라우트와 테스트가 모두 이 함수들을 사용한다."""

import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import db
from .models import (
    ACTIVE_STATUSES,
    CALLED,
    CANCELLED,
    DONE,
    NO_SHOW,
    WAITING,
    QueueEntry,
    Setting,
)

# 한국은 서머타임이 없어 고정 오프셋으로 충분 (Windows 에 tzdata 가 없어도 동작)
KST = timezone(timedelta(hours=9))

NAME_RE = re.compile(r"^[가-힣]{2,4}$")
PHONE_RE = re.compile(r"^[0-9]{4}$")
NAME_ERROR = "이름은 한글 2~4자로 입력해주세요"
PHONE_ERROR = "전화번호 뒷자리 4자리를 입력해주세요"
MASK = "○"


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class ClosedError(Exception):
    pass


def now() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def today() -> date:
    return now().date()


# ---------- 검증 · 마스킹 ----------

def clean_name(raw: str) -> str:
    # iOS 등에서 자모가 분리된(NFD) 상태로 올 수 있어 합쳐서 검사
    return unicodedata.normalize("NFC", raw or "").strip()


def clean_phone(raw: str) -> str:
    return (raw or "").strip()


def validate_entry(raw_name: str, raw_phone: str) -> tuple[str, str]:
    name, phone = clean_name(raw_name), clean_phone(raw_phone)
    if not NAME_RE.fullmatch(name):
        raise ValidationError("name", NAME_ERROR)
    if not PHONE_RE.fullmatch(phone):
        raise ValidationError("phone", PHONE_ERROR)
    return name, phone


def mask_name(name: str | None) -> str:
    if not name:
        return MASK * 2
    if len(name) <= 2:
        return name[0] + MASK * (len(name) - 1)
    return name[0] + MASK * (len(name) - 2) + name[-1]


# ---------- 접수 마감 설정 ----------

def is_open(s: Session) -> bool:
    row = s.get(Setting, "accepting")
    return row is None or row.value == "1"


def set_open(value: bool) -> None:
    with db.SessionLocal() as s, s.begin():
        row = s.get(Setting, "accepting")
        if row is None:
            s.add(Setting(key="accepting", value="1" if value else "0"))
        else:
            row.value = "1" if value else "0"


def get_open() -> bool:
    with db.SessionLocal() as s:
        return is_open(s)


# ---------- 손님 ----------

def issue_ticket(raw_name: str, raw_phone: str) -> tuple[QueueEntry, bool]:
    """대기번호 발급. (접수 내역, 새로 발급했는지) 를 돌려준다.

    같은 이름+전화 뒷자리로 오늘 대기중/호출됨 접수가 있으면 그 접수를 그대로 돌려준다.
    """
    name, phone = validate_entry(raw_name, raw_phone)
    # SQLite 는 BEGIN IMMEDIATE 로 직렬화되지만, 다른 DB 에서는
    # (date, ticket_no) 유니크 제약 충돌 시 다시 시도한다.
    for _ in range(5):
        with db.SessionLocal() as s:
            try:
                with s.begin():
                    if not is_open(s):
                        raise ClosedError()
                    day = today()
                    existing = s.scalars(
                        select(QueueEntry).where(
                            QueueEntry.date == day,
                            QueueEntry.name == name,
                            QueueEntry.phone_last4 == phone,
                            QueueEntry.status.in_(ACTIVE_STATUSES),
                        )
                    ).first()
                    if existing:
                        return existing, False
                    last_no = s.scalar(
                        select(func.max(QueueEntry.ticket_no)).where(QueueEntry.date == day)
                    )
                    entry = QueueEntry(
                        ticket_no=(last_no or 0) + 1,
                        date=day,
                        name=name,
                        phone_last4=phone,
                        status=WAITING,
                        token=secrets.token_urlsafe(24),
                        created_at=now(),
                    )
                    s.add(entry)
                return entry, True
            except IntegrityError:
                continue
    raise RuntimeError("대기번호 발급에 실패했습니다")


def _active_today(s: Session, day: date) -> list[QueueEntry]:
    return list(
        s.scalars(
            select(QueueEntry)
            .where(QueueEntry.date == day, QueueEntry.status.in_(ACTIVE_STATUSES))
            .order_by(QueueEntry.ticket_no)
        )
    )


def public_queue(s: Session, day: date, mine_id: int | None = None) -> list[dict]:
    return [
        {
            "no": e.ticket_no,
            "name": mask_name(e.name),
            "status": e.status,
            "mine": e.id == mine_id,
        }
        for e in _active_today(s, day)
    ]


def get_public_state() -> dict:
    with db.SessionLocal() as s:
        day = today()
        queue = public_queue(s, day)
        return {"is_open": is_open(s), "waiting_count": len(queue), "queue": queue}


def get_entry_by_token(token: str) -> QueueEntry | None:
    if not token:
        return None
    with db.SessionLocal() as s:
        return s.scalars(select(QueueEntry).where(QueueEntry.token == token)).first()


def get_ticket_view(token: str) -> dict | None:
    with db.SessionLocal() as s:
        entry = s.scalars(select(QueueEntry).where(QueueEntry.token == token)).first()
        if entry is None:
            return None
        day = today()
        expired = entry.date != day
        queue = public_queue(s, day, entry.id) if not expired else []
        ahead = 0
        if entry.status in ACTIVE_STATUSES and not expired:
            ahead = sum(1 for q in queue if q["no"] < entry.ticket_no)
        return {
            "ticket_no": entry.ticket_no,
            "name": mask_name(entry.name),
            "status": entry.status,
            "ahead": ahead,
            "expired": expired,
            "date": entry.date.isoformat(),
            "is_open": is_open(s),
            "queue": queue,
        }


def cancel_ticket(token: str) -> bool:
    with db.SessionLocal() as s, s.begin():
        entry = s.scalars(select(QueueEntry).where(QueueEntry.token == token)).first()
        if entry is None or entry.status not in ACTIVE_STATUSES:
            return False
        entry.status = CANCELLED
        entry.completed_at = now()
        return True


# ---------- 관리자 ----------

ADMIN_ACTIONS = {
    # 동작: (허용되는 현재 상태, 바뀔 상태)
    "call": ((WAITING,), CALLED),
    "done": ((WAITING, CALLED), DONE),
    "no_show": ((WAITING, CALLED), NO_SHOW),
    "restore": ((DONE, NO_SHOW, CANCELLED), None),  # 실수로 누른 처리를 되돌림
}


def admin_action(entry_id: int, action: str) -> bool:
    if action not in ADMIN_ACTIONS:
        return False
    allowed, target = ADMIN_ACTIONS[action]
    with db.SessionLocal() as s, s.begin():
        entry = s.get(QueueEntry, entry_id)
        if entry is None or entry.status not in allowed:
            return False
        if action == "restore":
            if entry.date != today():
                return False
            entry.status = CALLED if entry.called_at else WAITING
            entry.completed_at = None
        elif target == CALLED:
            entry.status = CALLED
            entry.called_at = now()
        else:
            entry.status = target
            entry.completed_at = now()
        return True


def _wait_minutes(e: QueueEntry) -> float | None:
    end = e.called_at or (e.completed_at if e.status == DONE else None)
    if end is None:
        return None
    return (end - e.created_at).total_seconds() / 60


def compute_stats(entries: list[QueueEntry]) -> dict:
    waits = [w for w in (_wait_minutes(e) for e in entries) if w is not None]
    count = lambda st: sum(1 for e in entries if e.status == st)  # noqa: E731
    return {
        "total": len(entries),
        "waiting": count(WAITING) + count(CALLED),
        "done": count(DONE),
        "cancelled": count(CANCELLED),
        "no_show": count(NO_SHOW),
        "avg_wait_min": round(sum(waits) / len(waits), 1) if waits else None,
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def get_admin_state() -> dict:
    with db.SessionLocal() as s:
        day = today()
        entries = list(
            s.scalars(
                select(QueueEntry).where(QueueEntry.date == day).order_by(QueueEntry.ticket_no)
            )
        )
        rows = [
            {
                "id": e.id,
                "no": e.ticket_no,
                "name": e.name,
                "phone": e.phone_last4,
                "status": e.status,
                "created_at": _iso(e.created_at),
                "called_at": _iso(e.called_at),
                "completed_at": _iso(e.completed_at),
            }
            for e in entries
        ]
        return {
            "is_open": is_open(s),
            "now": _iso(now()),
            "active": [r for r in rows if r["status"] in ACTIVE_STATUSES],
            "finished": [r for r in reversed(rows) if r["status"] not in ACTIVE_STATUSES],
            "stats": compute_stats(entries),
        }


# ---------- 개인정보 정리 ----------

def purge_personal_data(retention_days: int) -> int:
    """보관 기간이 지난 접수의 이름·전화번호를 지운다. 지운 건수를 돌려준다."""
    cutoff = today() - timedelta(days=retention_days)
    with db.SessionLocal() as s, s.begin():
        result = s.execute(
            update(QueueEntry)
            .where(
                QueueEntry.date < cutoff,
                (QueueEntry.name.is_not(None)) | (QueueEntry.phone_last4.is_not(None)),
            )
            .values(name=None, phone_last4=None)
        )
        return result.rowcount or 0
