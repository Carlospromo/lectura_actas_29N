from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def db_session():
    with Session() as db:
        yield db


def one(db, sql, params=None):
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def all_rows(db, sql, params=None):
    return [dict(r) for r in db.execute(text(sql), params or {}).mappings()]
