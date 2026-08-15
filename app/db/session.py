import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI の Depends 用ジェネレータ"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
