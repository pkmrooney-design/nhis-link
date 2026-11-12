from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


engine: Engine
SessionLocal: sessionmaker


def configure(url: str) -> None:
    """엔진을 (다시) 만든다. 테스트에서 DB를 바꿀 때도 사용."""
    global engine, SessionLocal
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn, _record):
            # 트랜잭션 시작을 직접 제어하기 위해 pysqlite 자동 BEGIN 끔
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=10000")
            cur.close()

        @event.listens_for(engine, "begin")
        def _on_begin(conn):
            # 트랜잭션 시작 즉시 쓰기 잠금을 잡아 동시 접수 시 번호 중복을 막음
            conn.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_all() -> None:
    from . import models  # noqa: F401  (테이블 등록)

    Base.metadata.create_all(engine)


configure(config.DATABASE_URL)
