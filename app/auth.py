"""Stdlib-only password hashing + HMAC signed tokens (no extra pip packages)."""
import base64, hashlib, hmac, json, os, time

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from . import config
from .db import User, get_db


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000)
        return hmac.compare_digest(new.hex(), dk)
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_token(user_id: int) -> str:
    body = _b64(json.dumps({"u": user_id, "exp": int(time.time()) + config.TOKEN_HOURS * 3600}).encode())
    sig = _b64(hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> int | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data["u"] if data["exp"] > time.time() else None
    except Exception:
        return None


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        raise HTTPException(401, "Login required")
    return user


def require(*roles):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Not allowed")
        return user
    return dep


def dashboard_access(authorization: str = Header(default=""), key: str = Query(default=""),
                     x_embed_key: str = Header(default=""), db: Session = Depends(get_db)):
    """CEO/admin token OR the read-only embed key (used by the Fertilizer app)."""
    k = key or x_embed_key
    if config.EMBED_KEY and k and hmac.compare_digest(k, config.EMBED_KEY):
        return None
    user = current_user(authorization, db)
    if user.role not in ("ceo", "admin"):
        raise HTTPException(403, "Dashboard is for CEO / admin")
    return user
