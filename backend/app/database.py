"""
Database setup.

We're using SQLite here because it needs zero configuration — the whole
database lives in one file (attune.db) that appears next to this code
the first time you run the app. That makes it perfect for learning.

When you're ready to deploy for real, the most common upgrade is to
swap SQLite for Postgres. Because we're going through SQLAlchemy,
that mostly just means changing DATABASE_URL below — the rest of the
code (models.py, routers/*) barely has to change. That's the whole
point of using an ORM.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file, if one exists

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./attune.db")

# check_same_thread is a SQLite-only quirk: it lets multiple requests
# share one connection safely for a simple dev server.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    FastAPI "dependency" — every route that needs the database asks for
    this function, gets a fresh session, and FastAPI guarantees it gets
    closed afterwards (even if the request raises an error).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
