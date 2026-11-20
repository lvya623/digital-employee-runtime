"""SQLAlchemy 持久化：默认 SQLite 即可跑通，改 DATABASE_URL 即切 PostgreSQL。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from der.config import settings

Base = declarative_base()


class TaskRecord(Base):
    __tablename__ = "der_tasks"

    task_id = Column(String(64), primary_key=True)
    status = Column(String(32), nullable=False)
    context_report = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EventRecord(Base):
    __tablename__ = "der_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), index=True, nullable=False)
    seq = Column(Integer, nullable=False)
    kind = Column(String(64), nullable=False)
    step_id = Column(String(64), nullable=True)
    detail = Column(JSON, default=dict)
    ts = Column(DateTime, nullable=False)


def make_engine(url: str | None = None):
    target = url or settings.database_url
    options: dict = {"future": True}
    if target.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(target, **options)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def make_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
