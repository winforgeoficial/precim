import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.cadence import Cadence, parse_cycle
from app.collector import scan_all
from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.search_collector import scan_all_searches

log = logging.getLogger("precim")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def _scan_everything() -> None:
    with SessionLocal() as session:
        await scan_all(session)
        await scan_all_searches(session)


def _schedule_next(scheduler: AsyncIOScheduler, cadence: Cadence) -> None:
    delay = cadence.next_delay_seconds()
    log.info("próxima varredura em %.0f min", delay / 60)
    scheduler.add_job(
        _run_and_reschedule, "date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=delay),
        args=[scheduler, cadence],
    )


async def _run_and_reschedule(scheduler: AsyncIOScheduler, cadence: Cadence) -> None:
    try:
        await _scan_everything()
    except Exception:
        log.exception("varredura falhou")
    finally:  # sempre agenda a próxima, mesmo após erro
        _schedule_next(scheduler, cadence)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    _schedule_next(scheduler, Cadence(parse_cycle(settings.scan_cycle_minutes)))
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="precim", version="0.2.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mascote": "🐷 de olho nas ofertas"}


# Painel web (build do Vite). Precisa vir por último para não esconder /api e /health.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="painel")
