"""
Creates one Admin account by prompting for name/email/password —
deliberately the *only* way to create one. There's no signup route
anywhere in the API (see models.Admin's docstring for why: closing off
the obvious attack of a hypothetical /api/admin/auth/signup endpoint).

Run from the backend/ folder, against whichever DATABASE_URL you want
the account created on — local SQLite or production Postgres, same as
seed.py:

    python create_admin.py
"""
import getpass

from app.database import SessionLocal, engine, Base
from app import models
from app.security import hash_password

Base.metadata.create_all(bind=engine)


def create_admin(db, name: str, email: str, password: str) -> models.Admin:
    existing = db.query(models.Admin).filter(models.Admin.email == email).first()
    if existing:
        raise ValueError(f"An admin with email {email!r} already exists.")
    admin = models.Admin(name=name, email=email, hashed_password=hash_password(password))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


if __name__ == "__main__":
    db = SessionLocal()
    try:
        name = input("Name: ").strip()
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")
        admin = create_admin(db, name, email, password)
        print(f"Created admin: {admin.email}")
    finally:
        db.close()
