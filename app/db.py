from datetime import datetime, date
from sqlalchemy import (create_engine, inspect, text, String, Integer, Float, Date, DateTime, Boolean,
                        ForeignKey, UniqueConstraint, CheckConstraint, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

import secrets

_kw = {"connect_args": {"check_same_thread": False}} if config.DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
engine = create_engine(config.DATABASE_URL, **_kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Estate(Base):
    __tablename__ = "ls_estates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    region: Mapped[str] = mapped_column(String(2))  # HG / LG
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only estates with their own factory can have logins and submit readings.
    has_factory: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "ls_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str| None] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))
    estate_id: Mapped[int | None] = mapped_column(ForeignKey("ls_estates.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # A long random secret embedded in this user's personal QR code
    # Anyone who scans it is logged in as this user
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(32))


class Reading(Base):
    __tablename__ = "ls_readings"
    __table_args__ = (
        UniqueConstraint("estate_id", "reading_date", "session", "submitted_by", name="uq_ls_reading"),
        CheckConstraint("leaf_standard >= 0 AND leaf_standard <= 1", name="ck_ls_range"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estate_id: Mapped[int] = mapped_column(ForeignKey("ls_estates.id"), index=True)
    reading_date: Mapped[date] = mapped_column(Date, index=True)
    session: Mapped[str] = mapped_column(String(10))  # morning / noon / evening
    leaf_standard: Mapped[float] = mapped_column(Float)  # fraction 0-1
    sample_good_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_total_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    remarks: Mapped[str] = mapped_column(Text, default="")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("ls_users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Audit(Base):
    __tablename__ = "ls_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FactorySupply(Base):
    """Which estates a factory may enter readings for (besides its own).

    Keyed by ESTATE, not by user, so the rule survives if a login is
    deleted and recreated. Replaces the old per-user FactoryAccess table.
    """
    __tablename__ = "ls_factory_supply"
    __table_args__ = (UniqueConstraint("factory_estate_id", "supplied_estate_id", name="uq_ls_factory_supply"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    factory_estate_id: Mapped[int] = mapped_column(ForeignKey("ls_estates.id"), index=True)
    supplied_estate_id: Mapped[int] = mapped_column(ForeignKey("ls_estates.id"), index=True)


def _migrate() -> None:
    """Upgrade an existing database in place (no need to delete it)."""
    cols = {c["name"] for c in inspect(engine).get_columns("ls_estates")}
    if "has_factory" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE ls_estates ADD COLUMN has_factory BOOLEAN NOT NULL DEFAULT FALSE"))


def _seed_factories(s) -> None:
    """First run only: load the default factory rules from config.py.

    Skipped once any factory or supply row exists, so it never overwrites
    what the admin has set from the Settings page.
    """
    if s.query(FactorySupply).count() or s.query(Estate).filter(Estate.has_factory).count():
        return
    by_name = {e.name: e for e in s.query(Estate).all()}
    for factory, supplied in config.DEFAULT_FACTORY_SUPPLY.items():
        f = by_name.get(factory)
        if not f:
            continue
        f.has_factory = True
        for name in supplied:
            t = by_name.get(name)
            if t and t.id != f.id:
                s.add(FactorySupply(factory_estate_id=f.id, supplied_estate_id=t.id))
    s.commit()


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate()
    with SessionLocal() as s:
        if s.query(Estate).count() == 0:
            for i, (n, r) in enumerate(config.ESTATES):
                s.add(Estate(name=n, region=r, sort_order=i))
            s.commit()
        _seed_factories(s)


def get_db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()