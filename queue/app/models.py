from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

WAITING = "waiting"
CALLED = "called"
DONE = "done"
CANCELLED = "cancelled"
NO_SHOW = "no_show"

ACTIVE_STATUSES = (WAITING, CALLED)


class QueueEntry(Base):
    __tablename__ = "queue_entries"
    __table_args__ = (UniqueConstraint("date", "ticket_no", name="uq_date_ticket"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_no: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 보관 기간이 지나면 NULL 로 지워짐
    name: Mapped[str | None] = mapped_column(String(10), nullable=True)
    phone_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WAITING)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 모든 시각은 한국 시간(KST) 기준, 시간대 정보 없이 저장
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
