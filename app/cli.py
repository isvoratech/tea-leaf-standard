"""Admin CLI.

  python -m app.cli init
  python -m app.cli add-user <username> <password> <role> [estate_name] [full name]
  python -m app.cli create-estate-users <default_password>   # one user per estate: calsay, clarendon ...
  python -m app.cli passwd <username> <new_password>
  python -m app.cli list
  python -m app.cli grant-estate <factory_username> <estate_name>
  python -m app.cli qr-link <username> [base_url]
  python -m app.cli regenerate-qr <username>
"""
import sys
import secrets

from sqlalchemy import select

from .auth import hash_password
from .db import Estate, FactoryAccess, SessionLocal, User, init_db


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
            full = " ".join(argv[5 if role == "estate" else 4:])
            if s.scalar(select(User).where(User.username == uname)):
                sys.exit("User exists")
            s.add(User(username=uname, password_hash=hash_password(pw), role=role,
                       estate_id=est.id if est else None, full_name=full))
            s.commit(); print(f"Created {role} user {uname}")
        elif cmd == "create-estate-users":
            pw = argv[1]
            for e in s.scalars(select(Estate).order_by(Estate.sort_order)):
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
        elif cmd == "grant-estate":
            uname, estate_name = argv[1].lower(), argv[2]
            u = s.scalar(select(User).where(User.username == uname))
            if not u:
                sys.exit(f"No such user {uname}")
            est = s.scalar(select(Estate).where(Estate.name.ilike(estate_name)))
            if not est:
                sys.exit(f"Unknown estate {estate_name}")
            if s.scalar(select(FactoryAccess).where(FactoryAccess.user_id == u.id, FactoryAccess.estate_id == est.id)):
                print("Already granted"); return
            s.add(FactoryAccess(user_id=u.id, estate_id=est.id))
            s.commit()
            print(f"{uname} can now submit for {est.name}")
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
            print(f"New QR token set for {argv[1]} — the old QR code is now invalid and must be reprinted.")
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])