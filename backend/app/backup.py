"""Cópia diária do banco SQLite (API de backup do SQLite: segura mesmo com o app em uso)."""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

log = logging.getLogger("precim.backup")
PREFIX = "precim-"


def db_path() -> Path | None:
    url = settings.database_url
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") else None


def backup_dir() -> Path | None:
    if settings.backup_dir:
        return Path(settings.backup_dir)
    path = db_path()
    return path.parent / "backups" if path else None


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob(f"{PREFIX}*.db"))


def is_recent(directory: Path, within: timedelta = timedelta(hours=24)) -> bool:
    files = _files(directory)
    if not files:
        return False
    modified = datetime.fromtimestamp(files[-1].stat().st_mtime, timezone.utc)
    return datetime.now(timezone.utc) - modified < within


def run_backup(keep: int | None = None) -> Path | None:
    """Faz a cópia e apaga as mais antigas. None se não houver o que copiar."""
    source, directory = db_path(), backup_dir()
    if not source or not directory or not source.exists():
        return None
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{PREFIX}{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    for old in _files(directory)[: -max(keep or settings.backup_keep, 1)]:
        old.unlink(missing_ok=True)
    log.info("backup do banco: %s", target.name)
    return target


def backup_if_needed() -> None:
    directory = backup_dir()
    if directory and is_recent(directory):
        return
    try:
        run_backup()
    except (OSError, sqlite3.Error):
        log.exception("backup do banco falhou")
