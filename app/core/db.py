from pathlib import Path
from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.base import Base

_engine = None
SessionLocal = None


def resolve_database_url(url: str, data_dir: Path) -> str:
    if url.startswith("sqlite:///./"):
        rel = url.removeprefix("sqlite:///./")
        path = (Path.cwd() / rel).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rest = url.removeprefix("sqlite:///")
        if not Path(rest).is_absolute():
            path = (data_dir / rest).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path}"
    return url


def init_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        return
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    resolved = resolve_database_url(settings.database_url, settings.data_dir)
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    _engine = create_engine(resolved, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_engine():
    init_engine()
    assert _engine is not None
    return _engine


def get_db() -> Generator[Session, None, None]:
    init_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]

__all__ = ["Base", "get_db", "get_engine", "init_engine", "resolve_database_url", "DbSession"]
