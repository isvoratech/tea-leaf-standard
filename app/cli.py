"""Admin CLI.

  python -m app.cli init
  python -m app.cli add-user <username> <password> <role> [estate_name] [full name]
  python -m app.cli create-estate-users <default_password>   # one user per estate: calsay, clarendon ...
  python -m app.cli passwd <username> <new_password>
  python -m app.cli list
"""
import sys

from sqlalchemy import select

from .auth import hash_password
from .db import Estate, SessionLocal, User, init_db


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
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
