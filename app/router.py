from datetime import date, datetime, timedelta
from io import BytesIO
import secrets  # CHANGED: needed for QR regenerate
from zoneinfo import ZoneInfo

import qrcode  # CHANGED: QR code image generation
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import config
from .auth import (current_user, dashboard_access, hash_password, make_token, require,
                   verify_google_id_token, verify_password)
from .db import Audit, DashboardSetting, Estate, FactorySupply, Person, Reading, ReadingLog, User, get_db

router = APIRouter(prefix="/api")


def today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def audit(db, user, action, detail=""):
    db.add(Audit(user_id=user.id if user else None, action=action, detail=detail))


# ---------------------------------------------------------------- who may enter for whom
def allowed_estate_ids(user: User, db: Session) -> set[int]:
    """Estates this login may submit / view readings for.

    Only an estate that HAS A FACTORY can enter data. It can always enter
    for itself, plus whichever estates the admin ticked for it on the
    Users page. An estate without a factory gets an empty set here - but
    note that viewing its OWN history no longer depends on this set (see
    my_readings below); this function now only gates submitting, and
    viewing estates OTHER than your own.
    """
    if user.role != "estate" or not user.estate_id:
        return set()
    own = db.get(Estate, user.estate_id)
    if not own or not own.active or not own.has_factory:
        return set()
    ids = {own.id}
    ids.update(db.scalars(
        select(FactorySupply.supplied_estate_id)
        .join(Estate, Estate.id == FactorySupply.supplied_estate_id)
        .where(FactorySupply.factory_estate_id == own.id, Estate.active)
    ).all())
    return ids


# ---------------------------------------------------------------- names for display
def _names_for(db: Session, user_ids: set[int]) -> dict[int, str]:
    """Map user id -> display name (their estate's name if they're an
    estate login, else their full name / username). Used so readings can
    show WHICH factory entered a value, not just an anonymous count."""
    if not user_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    estate_ids = {u.estate_id for u in users if u.estate_id}
    estate_names = {e.id: e.name for e in db.scalars(
        select(Estate).where(Estate.id.in_(estate_ids)))} if estate_ids else {}
    return {u.id: (estate_names.get(u.estate_id) or u.full_name or u.username) for u in users}


# ---------------------------------------------------------------- person (Google identity)
def _person(db: Session, user: User) -> Person | None:
    """The person attached to this session (see /identify), unless blocked."""
    pid = getattr(user, "person_id", None)
    p = db.get(Person, pid) if pid else None
    return p if p and not p.blocked else None


def _person_out(p: Person | None):
    return {"id": p.id, "name": p.name, "email": p.email} if p else None


def _upsert_person(db: Session, info: dict) -> Person:
    """Find or create the person for a verified Google token. No approval
    needed - the first sign-in simply records who they are."""
    email = info["email"].strip().lower()
    p = db.scalar(select(Person).where(Person.email == email))
    now = datetime.utcnow()
    if p is None:
        p = Person(email=email, name=info.get("name") or email, google_sub=info.get("sub"),
                   first_seen=now, last_seen=now, blocked=False)
        db.add(p)
    else:
        p.name = info.get("name") or p.name
        p.google_sub = p.google_sub or info.get("sub")
        p.last_seen = now
    db.flush()
    return p


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str
    password: str


def user_out(u: User, db: Session, person: Person | None = None):
    est = db.get(Estate, u.estate_id) if u.estate_id else None
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "estate_id": u.estate_id, "estate": est.name if est else None, "active": u.active,
            # Frontend uses this to decide entry-form vs read-only view.
            "has_factory": est.has_factory if est else None,
            "email": u.email,
            # Who is using this login on this phone (Google account), or null.
            "person": _person_out(person)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    audit(db, u, "login"); db.commit()
    return {"token": make_token(u.id), "user": user_out(u, db)}


class GoogleIn(BaseModel):
    credential: str


@router.post("/google-login")
def google_login(body: GoogleIn, db: Session = Depends(get_db)):
    """Login-page Google button: signs in the user whose email the admin
    linked on the Users page (mainly CEO / admin)."""
    info = verify_google_id_token(body.credential)
    if not info:
        raise HTTPException(401, "Google sign-in failed")
    email = info["email"].strip().lower()
    u = db.scalar(select(User).where(User.email == email))
    if not u or not u.active:
        audit(db, None, "google_login_denied", email); db.commit()
        raise HTTPException(403, "This Google account is not linked to a Leaf Standard user - contact admin")
    p = _upsert_person(db, info)
    if p.blocked:
        raise HTTPException(403, "This Google account has been blocked - contact admin")
    audit(db, u, "google_login", email); db.commit()
    return {"token": make_token(u.id, p.id), "user": user_out(u, db, p)}


@router.post("/identify")
def identify(body: GoogleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """After scanning an estate QR: record WHO is using this estate login.
    Returns a new session token that carries both the login and the person."""
    info = verify_google_id_token(body.credential)
    if not info:
        raise HTTPException(401, "Google sign-in failed")
    p = _upsert_person(db, info)
    if p.blocked:
        audit(db, user, "identify_blocked", p.email); db.commit()
        raise HTTPException(403, "This Google account has been blocked - contact admin")
    audit(db, user, "identify", f"{p.email} ({p.name}) on {user.username}")
    db.commit()
    return {"token": make_token(user.id, p.id), "user": user_out(user, db, p)}


@router.post("/forget-person")
def forget_person(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """'Not you?' - drop the person from this phone's session, keep the estate login."""
    return {"token": make_token(user.id), "user": user_out(user, db)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(user, db, _person(db, user))


@router.get("/config")
def public_config():
    return {"target": config.TARGET, "warn": config.WARN, "sessions": config.SESSIONS,
            "today": today().isoformat(), "edit_days": config.EDIT_DAYS,
            "google_client_id": config.GOOGLE_CLIENT_ID}


def _dashboard_remarks_visible(db: Session) -> bool:
    setting = db.scalar(select(DashboardSetting).where(DashboardSetting.key == "show_remarks"))
    return True if setting is None else bool(setting.value)


class RemarkVisibilityIn(BaseModel):
    show: bool


@router.get("/admin/settings/remarks")
def admin_remarks_setting(_: User = Depends(require("admin")), db: Session = Depends(get_db)):
    return {"show": _dashboard_remarks_visible(db)}


@router.put("/admin/settings/remarks")
def update_admin_remarks_setting(body: RemarkVisibilityIn, admin: User = Depends(require("admin")),
                                db: Session = Depends(get_db)):
    setting = db.scalar(select(DashboardSetting).where(DashboardSetting.key == "show_remarks"))
    if setting is None:
        setting = DashboardSetting(key="show_remarks", value=body.show)
        db.add(setting)
    else:
        setting.value = body.show
    audit(db, admin, "dashboard_remarks_visibility", f"show={body.show}")
    db.commit()
    return {"show": bool(setting.value)}


@router.get("/estates")
def estates(db: Session = Depends(get_db)):
    rows = db.scalars(select(Estate).where(Estate.active).order_by(Estate.sort_order)).all()
    return [{"id": e.id, "name": e.name, "region": e.region, "has_factory": e.has_factory} for e in rows]


@router.get("/my-estates")
def my_estates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "estate":
        # admin/ceo can see every active estate
        rows = db.scalars(select(Estate).where(Estate.active).order_by(Estate.sort_order)).all()
        return [{"id": e.id, "name": e.name} for e in rows]

    allowed = allowed_estate_ids(user, db)
    if not allowed:
        return []  # this estate has no factory -> nothing to enter (own history is a separate endpoint)

    # Own estate first, so the frontend dropdown defaults to it.
    rest = db.scalars(select(Estate).where(Estate.id.in_(allowed - {user.estate_id}))
                      .order_by(Estate.sort_order)).all()
    ordered = [db.get(Estate, user.estate_id)] + list(rest)
    return [{"id": e.id, "name": e.name} for e in ordered]


# ---------------------------------------------------------------- estate entry
class ReadingIn(BaseModel):
    reading_date: date
    session: str
    percent: float | None = Field(default=None, ge=0, le=100)
    sample_good_g: float | None = Field(default=None, ge=0)
    sample_total_g: float | None = Field(default=None, gt=0)
    remarks: str = ""
    estate_id: int | None = None  # admin, or a factory entering for another estate it supplies


def _save(body: ReadingIn, user: User, db: Session) -> Reading:
    if body.session not in config.SESSIONS:
        raise HTTPException(422, "session must be morning, noon or evening")
    if user.role == "admin" and body.estate_id:
        estate_id = body.estate_id
    elif user.role == "estate":
        allowed = allowed_estate_ids(user, db)
        if not allowed:
            raise HTTPException(403, "Your estate has no factory, so it cannot submit readings - contact admin")
        estate_id = body.estate_id or user.estate_id
        if estate_id not in allowed:
            raise HTTPException(403, "You are not authorized to submit for this estate")
    else:
        raise HTTPException(403, "Only estate users or admin can submit")
    if not db.get(Estate, estate_id):
        raise HTTPException(404, "Estate not found")

    # Who is entering: estate logins must have a Google identity attached.
    person = _person(db, user)
    if user.role == "estate" and not person:
        raise HTTPException(428, "Sign in with Google first so we know who is entering this reading")
    who_name = person.name if person else (user.full_name or user.username)
    who_email = person.email if person else (user.email or "")

    t = today()
    if body.reading_date > t:
        raise HTTPException(422, "Future dates are not allowed")
    if user.role == "estate" and (t - body.reading_date).days > config.EDIT_DAYS:
        raise HTTPException(403, f"Entries older than {config.EDIT_DAYS} day(s) are locked - contact admin")

    if body.sample_good_g is not None and body.sample_total_g:
        if body.sample_good_g > body.sample_total_g:
            raise HTTPException(422, "Good leaf weight cannot exceed total sample weight")
        frac = body.sample_good_g / body.sample_total_g
    elif body.percent is not None:
        frac = body.percent / 100
    else:
        raise HTTPException(422, "Enter leaf standard % or sample weights")

    # One reading per estate/date/session per login - a second person on the
    # same estate QR updates the same row (unchanged behaviour).
    r = db.scalar(select(Reading).where(Reading.estate_id == estate_id,
                                        Reading.reading_date == body.reading_date,
                                        Reading.session == body.session,
                                        Reading.submitted_by == user.id))
    now = datetime.utcnow()
    if r is None:
        r = Reading(estate_id=estate_id, reading_date=body.reading_date, session=body.session,
                    submitted_by=user.id, submitted_at=now)
        db.add(r)
        act = "reading_create"
    else:
        act = "reading_update"
    r.leaf_standard = round(frac, 4)
    r.sample_good_g, r.sample_total_g = body.sample_good_g, body.sample_total_g
    r.remarks = body.remarks[:500]
    r.updated_at = now
    r.entered_by_name, r.entered_by_email = who_name, who_email
    db.flush()  # get r.id for the log row
    db.add(ReadingLog(reading_id=r.id, estate_id=estate_id, reading_date=body.reading_date,
                      session=body.session, leaf_standard=r.leaf_standard,
                      action="create" if act == "reading_create" else "update",
                      entered_by_name=who_name, entered_by_email=who_email,
                      login_user_id=user.id, at=now))
    audit(db, user, act, f"estate={estate_id} {body.reading_date} {body.session} {r.leaf_standard} by {who_email or who_name}")
    return r


def reading_out(r: Reading, submitted_by_name: str | None = None):
    return {"id": r.id, "estate_id": r.estate_id, "reading_date": r.reading_date.isoformat(),
            "session": r.session, "leaf_standard": r.leaf_standard,
            "percent": round(r.leaf_standard * 100, 2), "sample_good_g": r.sample_good_g,
            "sample_total_g": r.sample_total_g, "remarks": r.remarks,
            "submitted_by": r.submitted_by,
            # Name of the factory/estate that submitted this reading, so a
            # read-only viewer can tell entries from different factories apart.
            "submitted_by_name": submitted_by_name,
            # The person (Google account) who last saved the value.
            "entered_by_name": r.entered_by_name, "entered_by_email": r.entered_by_email,
            "submitted_at": r.submitted_at.isoformat() + "Z", "updated_at": r.updated_at.isoformat() + "Z"}


@router.post("/readings")
def submit(body: ReadingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _save(body, user, db)
    db.commit()
    name = _names_for(db, {user.id}).get(user.id)
    return reading_out(r, name)


class BulkIn(BaseModel):
    items: list[ReadingIn]


@router.post("/readings/bulk")
def submit_bulk(body: BulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Offline queue sync from the phone. Each item is saved independently."""
    results = []
    name = _names_for(db, {user.id}).get(user.id)
    for it in body.items[:100]:
        try:
            r = _save(it, user, db)
            db.commit()
            results.append({"ok": True, "reading": reading_out(r, name)})
        except HTTPException as e:
            db.rollback()
            results.append({"ok": False, "error": e.detail, "item": it.model_dump(mode="json")})
    return {"results": results}


@router.get("/readings")
def my_readings(d: date | None = Query(default=None, alias="date"), days: int = 7,
                estate_id: int | None = None,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "estate":
        eid = estate_id or user.estate_id
        # Your OWN estate's history is always viewable, even with no
        # factory (read-only login). Only viewing a DIFFERENT estate
        # still requires factory-granted access via allowed_estate_ids.
        if eid != user.estate_id and eid not in allowed_estate_ids(user, db):
            raise HTTPException(403, "You are not authorized to view this estate")
    else:
        eid = estate_id

    if not eid:
        raise HTTPException(422, "estate_id required")

    end = d or today()
    start = end - timedelta(days=max(0, min(days, 62)) - 1) if days > 1 else end
    rows = db.scalars(select(Reading).where(Reading.estate_id == eid, Reading.reading_date >= start,
                                            Reading.reading_date <= end)
                      .order_by(Reading.reading_date.desc())).all()
    # Resolve submitter names in one batch and attach to each row so the
    # frontend can show which factory entered which value.
    names = _names_for(db, {r.submitted_by for r in rows})
    return [reading_out(r, names.get(r.submitted_by)) for r in rows]


class RemarkIn(BaseModel):
    remarks: str = Field(default="", max_length=500)


@router.put("/readings/{rid}/remark")
def update_reading_remark(
    rid: int,
    body: RemarkIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update only the optional remark.

    This does NOT change the leaf-standard value and does NOT create
    another ReadingLog value-history record.
    """
    r = db.get(Reading, rid)

    if not r:
        raise HTTPException(404, "Reading not found")

    if user.role not in ("admin", "estate"):
        raise HTTPException(403, "Not allowed")

    if user.role == "estate":
        if r.submitted_by != user.id:
            raise HTTPException(403, "You can only edit remarks on your own reading")

        if not _person(db, user):
            raise HTTPException(
                428,
                "Sign in with Google first so we know who is editing this remark"
            )

        if (today() - r.reading_date).days > config.EDIT_DAYS:
            raise HTTPException(
                403,
                f"Entries older than {config.EDIT_DAYS} day(s) are locked - contact admin"
            )

    r.remarks = body.remarks.strip()[:500]

    audit(
        db,
        user,
        "reading_remark_update",
        f"reading={r.id} estate={r.estate_id} "
        f"{r.reading_date} {r.session}"
    )

    db.commit()

    name = _names_for(db, {r.submitted_by}).get(r.submitted_by)
    return reading_out(r, name)


@router.delete("/readings/{rid}")
def delete_reading(rid: int, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    r = db.get(Reading, rid)
    if not r:
        raise HTTPException(404, "Not found")
    audit(db, user, "reading_delete", f"{rid} estate={r.estate_id} {r.reading_date} {r.session}")
    db.delete(r); db.commit()
    return {"ok": True}


@router.get("/qr-login")
def qr_login(token: str, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.qr_token == token))
    if not u or not u.active:
        raise HTTPException(401, "Invalid or revoked QR code")
    audit(db, u, "qr_login")
    db.commit()
    return {"token": make_token(u.id), "user": user_out(u, db)}


# ---------------------------------------------------------------- CEO dashboard
def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def build_summary(db: Session, start: date, end: date, include_remarks: bool = True):
    if end < start:
        start, end = end, start
    ests = db.scalars(select(Estate).where(Estate.active).order_by(Estate.sort_order)).all()
    reads = db.scalars(select(Reading).where(Reading.reading_date >= start,
                                             Reading.reading_date <= end)).all()
    bucket: dict[tuple, list] = {}
    slots: dict[int, set] = {}
    days_seen: dict[int, set] = {}
    last: dict[int, datetime] = {}
    remarks: dict[int, list] = {}
    session_remarks: dict[int, dict[str, list]] = {}
    # (estate, session) -> {login id: [values]}  - per-factory split
    fac_bucket: dict[tuple, dict[int, list]] = {}
    for r in reads:
        bucket.setdefault((r.estate_id, r.session), []).append(r.leaf_standard)
        fac_bucket.setdefault((r.estate_id, r.session), {}).setdefault(r.submitted_by, []).append(r.leaf_standard)
        # A "slot" is one date + session. Several factories can fill the same
        # slot for an estate; it still only counts once towards completeness.
        slots.setdefault(r.estate_id, set()).add((r.reading_date, r.session))
        days_seen.setdefault(r.estate_id, set()).add(r.reading_date)
        if r.estate_id not in last or r.updated_at > last[r.estate_id]:
            last[r.estate_id] = r.updated_at
        if include_remarks and r.remarks:
            remarks.setdefault(r.estate_id, []).append(f"{r.reading_date:%d %b} {r.session}: {r.remarks}")
            session_remarks.setdefault(r.estate_id, {}).setdefault(r.session, []).append(
                (r.reading_date, f"{r.reading_date:%d %b}: {r.remarks}")
            )

    fac_names = _names_for(db, {r.submitted_by for r in reads})

    ndays = (end - start).days + 1
    rows, groups = [], {"HG": [], "LG": []}
    for e in ests:
        vals = {s: _avg(bucket.get((e.id, s), [])) for s in config.SESSIONS}
        count = len(slots.get(e.id, ()))
        remarks_by_session = {
            session: [text for _, text in sorted(session_remarks.get(e.id, {}).get(session, []))][-5:]
            for session in config.SESSIONS
        } if include_remarks else {session: [] for session in config.SESSIONS}

        # Factory-wise values - only for sessions entered by 2+ factories
        by_factory = {}
        for s in config.SESSIONS:
            per = fac_bucket.get((e.id, s), {})
            if len(per) > 1:
                by_factory[s] = sorted(
                    ({"name": fac_names.get(uid, f"User {uid}"), "value": _avg(v)} for uid, v in per.items()),
                    key=lambda x: x["name"])

        row = {"type": "estate", "estate_id": e.id, "name": e.name, "region": e.region, **vals,
               "day_avg": _avg(list(vals.values())), "submitted": count, "expected": 3 * ndays,
               "days_reported": len(days_seen.get(e.id, ())),
               "last_update": last[e.id].isoformat() + "Z" if e.id in last else None,
               "remarks": remarks.get(e.id, [])[-5:] if include_remarks else [],
               "remarks_by_session": remarks_by_session,
               "by_factory": by_factory}
        groups.setdefault(e.region, []).append(row)

    def avg_row(label, key, members):
        vals = {s: _avg([m[s] for m in members]) for s in config.SESSIONS}
        return {"type": "avg", "name": label, "key": key, **vals, "day_avg": _avg(list(vals.values())),
                "submitted": sum(m["submitted"] for m in members),
                "expected": sum(m["expected"] for m in members)}

    rows += groups["HG"]; rows.append(avg_row("AVG High Grown", "HG", groups["HG"]))
    rows += groups["LG"]; rows.append(avg_row("AVG Low Grown", "LG", groups["LG"]))
    all_e = groups["HG"] + groups["LG"]
    company = avg_row("AVG Company", "ALL", all_e)
    rows.append(company)
    return {"from": start.isoformat(), "to": end.isoformat(), "days": ndays, "rows": rows,
            "status": {"submitted": company["submitted"], "expected": company["expected"],
                       "estates_complete": sum(1 for m in all_e if m["submitted"] >= m["expected"]),
                       "estates_missing": [m["name"] for m in all_e if m["submitted"] == 0],
                       "estates_total": len(all_e)},
            "target": config.TARGET, "warn": config.WARN}


def _range(d, frm, to):
    if frm and to:
        return frm, to
    x = d or frm or to or today()
    return x, x


@router.get("/summary")
def summary(d: date | None = Query(default=None, alias="date"), frm: date | None = Query(default=None, alias="from"),
            to: date | None = None, _=Depends(dashboard_access), db: Session = Depends(get_db)):
    s, e = _range(d, frm, to)
    if (e - s).days > 366:
        raise HTTPException(422, "Max range is 1 year")
    show_remarks = _dashboard_remarks_visible(db)
    data = build_summary(db, s, e, include_remarks=show_remarks)
    data["remarks_visible"] = show_remarks
    return data


@router.get("/trend")
def trend(days: int = 14, end: date | None = None,
          frm: date | None = Query(default=None, alias="from"),
          to: date | None = None,
          estate_id: int | None = None,
          _=Depends(dashboard_access), db: Session = Depends(get_db)):

    if (frm is None) != (to is None):
        raise HTTPException(422, "Provide both from and to dates")

    if frm is not None:
        if to < frm or (to - frm).days > 366:
            raise HTTPException(
                422,
                "Choose an ordered range of at most 367 days"
            )

        start, end = frm, to
        days = (end - start).days + 1

    else:
        end = end or today()
        days = max(2, min(days, 90))
        start = end - timedelta(days=days - 1)

    estates = db.scalars(
        select(Estate)
        .where(Estate.active)
        .order_by(Estate.sort_order)
    ).all()

    selected_estate = None

    if estate_id is not None:
        selected_estate = next(
            (e for e in estates if e.id == estate_id),
            None
        )

        if selected_estate is None:
            raise HTTPException(
                404,
                "Estate not found or inactive"
            )

    reads = db.scalars(
        select(Reading).where(
            Reading.reading_date >= start,
            Reading.reading_date <= end
        )
    ).all()

    bucket: dict = {}

    for r in reads:
        bucket.setdefault(
            (
                r.reading_date,
                r.estate_id,
                r.session
            ),
            []
        ).append(r.leaf_standard)

    # Per-factory values for the selected estate (used only where 2+ factories entered)
    fac: dict[tuple, dict[int, list]] = {}
    if selected_estate is not None:
        for r in reads:
            if r.estate_id == selected_estate.id:
                fac.setdefault((r.reading_date, r.session), {}).setdefault(r.submitted_by, []).append(r.leaf_standard)
    fac_names = _names_for(db, {uid for per in fac.values() for uid in per})

    out = []

    for i in range(days):
        dd = start + timedelta(days=i)

        members = [
            (
                e.region,
                {
                    session: _avg(
                        bucket.get(
                            (
                                dd,
                                e.id,
                                session
                            ),
                            []
                        )
                    )
                    for session in config.SESSIONS
                }
            )
            for e in estates
            if e.region in ("HG", "LG")
        ]

        point = {
            "date": dd.isoformat()
        }

        for key in ("HG", "LG", "ALL"):
            selected = [
                values
                for region, values in members
                if key == "ALL" or region == key
            ]

            point[key] = _avg([
                _avg([
                    member[session]
                    for member in selected
                ])
                for session in config.SESSIONS
            ])

        # Optional selected-estate daily average.
        # Same calculation principle:
        # average readings inside each session,
        # then average Morning / Noon / Evening.
        if selected_estate is not None:

            estate_sessions = {
                session: _avg(
                    bucket.get(
                        (
                            dd,
                            selected_estate.id,
                            session
                        ),
                        []
                    )
                )
                for session in config.SESSIONS
            }

            point["ESTATE"] = _avg(
                list(estate_sessions.values())
            )
            # Per-session values for the "View daily values" table
            point["ESTATE_SESSIONS"] = estate_sessions

            point["ESTATE_FACTORIES"] = {
                s: sorted(
                    ({"name": fac_names.get(uid, f"User {uid}"), "value": _avg(v)}
                     for uid, v in fac.get((dd, s), {}).items()),
                    key=lambda x: x["name"])
                for s in config.SESSIONS
                if len(fac.get((dd, s), {})) > 1
            }

        out.append(point)

    return out


@router.get("/export.xlsx")
def export(d: date | None = Query(default=None, alias="date"), frm: date | None = Query(default=None, alias="from"),
           to: date | None = None, _=Depends(dashboard_access), db: Session = Depends(get_db)):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    s, e = _range(d, frm, to)
    data = build_summary(db, s, e)
    wb = Workbook(); ws = wb.active; ws.title = "Sumamry"  # same sheet name as template
    thin = Side(style="thin", color="999999")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    bold = Font(bold=True)
    ws["D1"], ws["F1"] = "Date 01", "Date 02"
    ws["B2"], ws["C2"], ws["D2"], ws["E2"], ws["F2"] = "Period", "From", s, "To", e
    ws["D2"].number_format = ws["F2"].number_format = "yyyy-mm-dd"
    ws["B4"] = "Estate"; ws["D4"] = "Leaf Standard"; ws.merge_cells("D4:F4")
    ws["G4"] = "Day Avg"; ws["H4"] = "Entries"
    for c, lab in zip("DEF", ["Morning", "Noon", "Evening"]):
        ws[f"{c}5"] = lab
    for ref in ("B4", "D4", "G4", "H4", "D5", "E5", "F5"):
        ws[ref].font = bold; ws[ref].alignment = Alignment(horizontal="center")
    green, amber, red = (PatternFill("solid", fgColor=x) for x in ("C6EFCE", "FFEB9C", "FFC7CE"))
    avgfill = PatternFill("solid", fgColor="DDEBF7")
    r = 6
    for row in data["rows"]:
        ws.cell(r, 2, row["name"])
        for j, key in enumerate(["morning", "noon", "evening", "day_avg"]):
            c = ws.cell(r, 4 + j, row[key]); c.number_format = "0.0%"; c.border = box
            if row["type"] == "avg":
                c.fill = avgfill
            elif row[key] is not None:
                c.fill = green if row[key] >= data["target"] else amber if row[key] >= data["warn"] else red
        ws.cell(r, 8, f'{row["submitted"]}/{row["expected"]}')
        if row["type"] == "avg":
            ws.cell(r, 2).font = bold
        r += 1
    ws.column_dimensions["B"].width = 18
    for c in "CDEFGH":
        ws.column_dimensions[c].width = 11
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    name = f"Leaf_Standard_{s}" + (f"_to_{e}" if e != s else "") + ".xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- admin: who entered what
_SESS_ORDER = {s: i for i, s in enumerate(config.SESSIONS)}


@router.get("/admin/entries")
def admin_entries(frm: date | None = Query(default=None, alias="from"), to: date | None = None,
                  estate_id: int | None = None, history: bool = False,
                  _: User = Depends(dashboard_access), db: Session = Depends(get_db)):
    """Current value per slot with who entered it, or (history=true) every
    save ever made, including values that were later overwritten."""
    to = to or today()
    frm = frm or to
    if frm > to:
        frm, to = to, frm
    if (to - frm).days > 366:
        raise HTTPException(422, "Max range is 1 year")
    ests = {e.id: e for e in db.scalars(select(Estate)).all()}

    if history:
        q = select(ReadingLog).where(ReadingLog.reading_date >= frm, ReadingLog.reading_date <= to)
        if estate_id:
            q = q.where(ReadingLog.estate_id == estate_id)
        logs = db.scalars(q.order_by(ReadingLog.at.desc()).limit(5000)).all()
        names = _names_for(db, {x.login_user_id for x in logs if x.login_user_id})
        return [{"estate": ests[x.estate_id].name if x.estate_id in ests else x.estate_id,
                 "estate_id": x.estate_id, "date": x.reading_date.isoformat(), "session": x.session,
                 "percent": round(x.leaf_standard * 100, 2), "action": x.action,
                 "entered_by_name": x.entered_by_name, "entered_by_email": x.entered_by_email,
                 "via": names.get(x.login_user_id), "time": x.at.isoformat() + "Z"} for x in logs]

    q = select(Reading).where(Reading.reading_date >= frm, Reading.reading_date <= to)
    if estate_id:
        q = q.where(Reading.estate_id == estate_id)
    rows = db.scalars(q.limit(5000)).all()
    names = _names_for(db, {r.submitted_by for r in rows})
    rows.sort(key=lambda r: (-r.reading_date.toordinal(),
                             ests[r.estate_id].sort_order if r.estate_id in ests else 0,
                             _SESS_ORDER.get(r.session, 9)))
    return [{"id": r.id, "estate": ests[r.estate_id].name if r.estate_id in ests else r.estate_id,
             "estate_id": r.estate_id, "date": r.reading_date.isoformat(), "session": r.session,
             "percent": round(r.leaf_standard * 100, 2), "remarks": r.remarks,
             "entered_by_name": r.entered_by_name, "entered_by_email": r.entered_by_email,
             "via": names.get(r.submitted_by), "time": r.updated_at.isoformat() + "Z"} for r in rows]


@router.delete("/admin/entries/{reading_id}")
def admin_delete_entry(reading_id: int, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    reading = db.get(Reading, reading_id)
    if not reading:
        raise HTTPException(404, "Entry not found")
    db.execute(delete(ReadingLog).where(ReadingLog.reading_id == reading_id))
    audit(db, admin, "entry_delete",
          f"reading_id={reading_id} estate_id={reading.estate_id} date={reading.reading_date} session={reading.session}")
    db.delete(reading)
    db.commit()
    return {"ok": True}


@router.get("/admin/people")
def admin_people(_: User = Depends(require("admin")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(ReadingLog.entered_by_email, func.count())
                             .group_by(ReadingLog.entered_by_email)).all())
    people = db.scalars(select(Person).order_by(Person.last_seen.desc())).all()
    return [{"id": p.id, "name": p.name, "email": p.email, "blocked": p.blocked,
             "first_seen": p.first_seen.isoformat() + "Z", "last_seen": p.last_seen.isoformat() + "Z",
             "saves": counts.get(p.email, 0)} for p in people]


class BlockIn(BaseModel):
    blocked: bool


@router.put("/admin/people/{pid}/block")
def admin_block(pid: int, body: BlockIn, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    p = db.get(Person, pid)
    if not p:
        raise HTTPException(404, "Not found")
    p.blocked = body.blocked
    audit(db, admin, "person_block" if body.blocked else "person_unblock", p.email)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- admin: factory access (managed from admin.html)
@router.get("/access")
def get_access(_: User = Depends(require("admin")), db: Session = Depends(get_db)):
    ests = db.scalars(select(Estate).order_by(Estate.sort_order)).all()
    supply: dict[int, list[int]] = {}
    for fs in db.scalars(select(FactorySupply)).all():
        supply.setdefault(fs.factory_estate_id, []).append(fs.supplied_estate_id)
    return {"estates": [{"id": e.id, "name": e.name, "region": e.region, "active": e.active,
                         "has_factory": e.has_factory} for e in ests],
            "supply": supply}


class FactoryFlagIn(BaseModel):
    has_factory: bool


@router.put("/estates/{eid}/factory")
def set_factory(eid: int, body: FactoryFlagIn, admin: User = Depends(require("admin")),
                db: Session = Depends(get_db)):
    e = db.get(Estate, eid)
    if not e:
        raise HTTPException(404, "Estate not found")
    e.has_factory = body.has_factory
    if not body.has_factory:
        db.execute(delete(FactorySupply).where(FactorySupply.factory_estate_id == eid))
    audit(db, admin, "factory_flag", f"{e.name} has_factory={body.has_factory}")
    db.commit()
    return {"ok": True}


class SupplyIn(BaseModel):
    estate_ids: list[int]


@router.put("/estates/{eid}/supply")
def set_supply(eid: int, body: SupplyIn, admin: User = Depends(require("admin")),
               db: Session = Depends(get_db)):
    f = db.get(Estate, eid)
    if not f:
        raise HTTPException(404, "Estate not found")
    if not f.has_factory:
        raise HTTPException(422, f"{f.name} is not marked as having a factory")
    names = {e.id: e.name for e in db.scalars(select(Estate)).all()}
    wanted = {i for i in body.estate_ids if i in names and i != eid}
    db.execute(delete(FactorySupply).where(FactorySupply.factory_estate_id == eid))
    for i in sorted(wanted):
        db.add(FactorySupply(factory_estate_id=eid, supplied_estate_id=i))
    audit(db, admin, "supply_update", f"{f.name} -> {', '.join(names[i] for i in sorted(wanted)) or 'own estate only'}")
    db.commit()
    return {"ok": True, "estate_ids": sorted(wanted)}


# ---------------------------------------------------------------- admin: users
class UserIn(BaseModel):
    username: str
    password: str | None = None
    full_name: str = ""
    role: str
    estate_id: int | None = None
    active: bool = True
    email: str | None = None


@router.get("/users")
def list_users(_: User = Depends(require("admin")), db: Session = Depends(get_db)):
    return [user_out(u, db) for u in db.scalars(select(User).order_by(User.role, User.username)).all()]


def _check(body: UserIn):
    if body.role not in ("estate", "ceo", "admin"):
        raise HTTPException(422, "role must be estate, ceo or admin")
    if body.role == "estate" and not body.estate_id:
        raise HTTPException(422, "Estate user needs an estate")
    if body.password is not None and len(body.password) < 6:
        raise HTTPException(422, "Password min 6 characters")


def _email(body: UserIn, db: Session, uid: int | None = None) -> str | None:
    e = (body.email or "").strip().lower() or None
    if e:
        if "@" not in e:
            raise HTTPException(422, "Invalid email")
        other = db.scalar(select(User).where(User.email == e))
        if other and other.id != uid:
            raise HTTPException(409, f"{e} is already linked to {other.username}")
    return e


# Estates no longer need a factory to be given a login - factory-less
# estates get a read-only login. Enforcement of "can this login submit
# readings" happens only at submit-time in _save() via
# allowed_estate_ids(), not at user create/update time.


@router.post("/users")
def create_user(body: UserIn, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    _check(body)
    if not body.password:
        raise HTTPException(422, "Password required")
    uname = body.username.strip().lower()
    if db.scalar(select(User).where(User.username == uname)):
        raise HTTPException(409, "Username exists")
    u = User(username=uname, full_name=body.full_name, role=body.role, active=body.active,
             estate_id=body.estate_id if body.role == "estate" else None,
             email=_email(body, db),
             password_hash=hash_password(body.password))
    db.add(u); audit(db, admin, "user_create", uname); db.commit()
    return user_out(u, db)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    _check(body)
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    u.full_name, u.role, u.active = body.full_name, body.role, body.active
    u.estate_id = body.estate_id if body.role == "estate" else None
    u.email = _email(body, db, u.id)
    if body.password:
        u.password_hash = hash_password(body.password)
    audit(db, admin, "user_update", u.username); db.commit()
    return user_out(u, db)

# ---------------------------------------------------------------- admin: QR codes
@router.get("/users/{uid}/qr.png")
def user_qr(uid: int, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    """A scannable QR code that logs this user in directly (no typing
    username/password). Encodes config.PUBLIC_URL + ?token=<qr_token>,
    which the frontend exchanges for a session via /api/qr-login."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    if not config.PUBLIC_URL:
        raise HTTPException(500, "LS_PUBLIC_URL is not set in .env - QR codes need the public login URL")
    url = f"{config.PUBLIC_URL}/?token={u.qr_token}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": f'inline; filename="qr_{u.username}.png"'})


@router.post("/users/{uid}/qr/regenerate")
def regenerate_qr(uid: int, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    """Invalidates the old QR code (old printed copy stops working) and
    issues a new token - use if a QR sheet is lost or compromised."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    u.qr_token = secrets.token_urlsafe(32)
    audit(db, admin, "qr_regenerate", u.username)
    db.commit()
    return {"ok": True}