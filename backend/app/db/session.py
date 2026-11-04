from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


# Colunas acrescentadas depois da primeira versão: (tabela, coluna, DDL)
_ADDED_COLUMNS = [
    ("hunt_offers", "source", "VARCHAR(20) NOT NULL DEFAULT 'buscape'"),
    ("hunt_offers", "verified", "BOOLEAN NOT NULL DEFAULT 0"),
    ("hunt_offers", "in_stock", "BOOLEAN"),
    ("hunt_offers", "approximate", "BOOLEAN NOT NULL DEFAULT 0"),
]


def _ensure_columns() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if table in insp.get_table_names() and column not in {
                c["name"] for c in insp.get_columns(table)
            }:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()


def get_session() -> Session:
    return SessionLocal()
