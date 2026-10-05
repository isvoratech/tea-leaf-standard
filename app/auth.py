"""Stdlib-only password hashing + HMAC signed tokens (no extra pip packages)."""
import base64, hashlib, hmac, json, os, time, urllib.parse, urllib.request

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


def make_token(user_id: int, person_id: int | None = None) -> str:
    """Session token. "u" = the login (estate QR / admin / CEO account).
    "p" = the person (Google account) using that login on this phone."""
    payload = {"u": user_id, "exp": int(time.time()) + config.TOKEN_HOURS * 3600}
    if person_id:
        payload["p"] = person_id
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _decode(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data if data["exp"] > time.time() else None
    except Exception:
        return None


def read_token(token: str) -> int | None:
    data = _decode(token)
    return data["u"] if data else None


def verify_google_id_token(id_token: str) -> dict | None:
    """Verify a Google ID token with Google's tokeninfo endpoint (stdlib only)."""
    if not config.GOOGLE_CLIENT_ID or not id_token:
        return None
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": id_token})
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    if data.get("aud") != config.GOOGLE_CLIENT_ID:
        return None
    if data.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    if str(data.get("email_verified")).lower() != "true":
        return None
    if int(data.get("exp", 0)) < time.time():
        return None
    if config.GOOGLE_ALLOWED_DOMAIN and (data.get("hd") or "").lower() != config.GOOGLE_DOMAIN:
        return None
    return data


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    data = _decode(token) if token else None
    user = db.get(User, data["u"]) if data else None
    if not user or not user.active:
        raise HTTPException(401, "Login required")
    # Not a DB column - just carried for this request (see router._person).
    user.person_id = data.get("p")
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
    token = authorization.removeprefix("Bearer ").strip()
    data = _decode(token) if token else None
    if data and data.get("role") == "ceo":
        return {"role": "ceo"}
    user = current_user(authorization, db)
    if user.role not in ("ceo", "admin"):
        raise HTTPException(403, "Dashboard is for CEO / admin")
    return user