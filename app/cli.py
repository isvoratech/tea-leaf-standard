"""Admin CLI.

  python -m app.cli init
  python -m app.cli add-user <username> <password> <role> [estate_name] [full name]
  python -m app.cli create-estate-users <default_password>   # one login per estate WITH A FACTORY
  python -m app.cli passwd <username> <new_password>
  python -m app.cli list
  python -m app.cli list-access                              # who may enter for whom
  python -m app.cli grant-estate <factory> <estate>          # factory = estate name or its username
  python -m app.cli revoke-estate <factory> <estate>
  python -m app.cli qr-link <username> [base_url]
  python -m app.cli regenerate-qr <username>

Most of this can also be done from the browser: /admin (users, factory flag, and access).
"""
import sys
import secrets

from sqlalchemy import select

from .auth import hash_password
from .db import Estate, FactorySupply, SessionLocal, User, init_db


def _find_factory(s, key):
    """Accepts an estate name ('Dessford') or a username ('dessford')."""
    est = s.scalar(select(Estate).where(Estate.name.ilike(key)))
    if not est:
        u = s.scalar(select(User).where(User.username == key.lower()))
        est = s.get(Estate, u.estate_id) if u and u.estate_id else None
    return est


def main(argv):
    init_db()
    if not argv or argv[0] == "init":
        print("Tables ready."); return
    cmd = argv[0]
    with SessionLocal() as s:
        if cmd == "add-user":
            uname, pw, role = argv[1].lower(), argv[2], argv[3]
            est = None
            if role == "estate":
                est = s.scalar(select(Estate).where(Estate.name.ilike(argv[4])))
                if not est:
                    sys.exit(f"Unknown estate {argv[4]}")
                # CHANGED: removed the has_factory check that used to block
                # login creation here. Any estate can now have a login -
                # estates without a factory simply get read-only access to
                # their own history (enforced at submit-time, not here).
            full = " ".join(argv[5 if role == "estate" else 4:])
            if s.scalar(select(User).where(User.username == uname)):
                sys.exit("User exists")
            s.add(User(username=uname, password_hash=hash_password(pw), role=role,
                       estate_id=est.id if est else None, full_name=full))
            s.commit(); print(f"Created {role} user {uname}")
        elif cmd == "create-estate-users":
            pw = argv[1]
            for e in s.scalars(select(Estate).where(Estate.has_factory).order_by(Estate.sort_order)):
                u = e.name.lower()
                if s.scalar(select(User).where(User.username == u)):
                    print(f"skip {u} (exists)"); continue
                s.add(User(username=u, password_hash=hash_password(pw), role="estate",
                           estate_id=e.id, full_name=f"{e.name} Estate"))
                print(f"created {u}")
            s.commit()
        elif cmd == "passwd":
            u = s.scalar(select(User).where(User.username == argv[1].lower()))
            if not u:
                sys.exit("No such user")
            u.password_hash = hash_password(argv[2]); s.commit(); print("Password changed")
        elif cmd == "list":
            for u in s.scalars(select(User).order_by(User.role, User.username)):
                print(f"{u.username:20} {u.role:7} estate_id={u.estate_id} active={u.active}")
        elif cmd == "list-access":
            names = {e.id: e.name for e in s.scalars(select(Estate))}
            for f in s.scalars(select(Estate).where(Estate.has_factory).order_by(Estate.sort_order)):
                ids = s.scalars(select(FactorySupply.supplied_estate_id)
                                .where(FactorySupply.factory_estate_id == f.id)).all()
                extra = sorted(names[i] for i in ids)
                print(f"{f.name:15} -> itself" + (f" + {', '.join(extra)}" if extra else ""))
        elif cmd in ("grant-estate", "revoke-estate"):
            fac = _find_factory(s, argv[1])
            if not fac or not fac.has_factory:
                sys.exit(f"'{argv[1]}' is not a factory estate")
            est = s.scalar(select(Estate).where(Estate.name.ilike(argv[2])))
            if not est:
                sys.exit(f"Unknown estate {argv[2]}")
            if fac.id == est.id:
                print("A factory can always enter for its own estate."); return
            row = s.scalar(select(FactorySupply).where(FactorySupply.factory_estate_id == fac.id,
                                                       FactorySupply.supplied_estate_id == est.id))
            if cmd == "grant-estate":
                if row:
                    print("Already granted"); return
                s.add(FactorySupply(factory_estate_id=fac.id, supplied_estate_id=est.id))
                s.commit(); print(f"{fac.name} can now enter readings for {est.name}")
            else:
                if not row:
                    print("Nothing to revoke"); return
                s.delete(row); s.commit(); print(f"{fac.name} can no longer enter readings for {est.name}")
        elif cmd == "qr-link":
            base_url = argv[2] if len(argv) > 2 else "http://localhost:8015"
            u = s.scalar(select(User).where(User.username == argv[1].lower()))
            if not u:
                sys.exit("No such user")
            print(f"{base_url}/?token={u.qr_token}")
        elif cmd == "regenerate-qr":
            u = s.scalar(select(User).where(User.username == argv[1].lower()))
            if not u:
                sys.exit("No such user")
            u.qr_token = secrets.token_urlsafe(32)
            s.commit()
            print(f"New QR token set for {argv[1]} - the old QR code is now invalid and must be reprinted.")
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])