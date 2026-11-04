import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api import router
from app.backup import backup_if_needed
from app.bot import start_bot, stop_bot
from app.cadence import Cadence, parse_cycle
from app.collector import scan_all
from app.core.config import settings
from app.db.models import HuntOffer
from app.db.session import SessionLocal, init_db
from app.search_collector import scan_all_searches

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # a URL do bot contém o token
log = logging.getLogger("precim")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def _scan_everything() -> None:
    with SessionLocal() as session:
        await scan_all(session)
        await scan_all_searches(session)


def _schedule_next(scheduler: AsyncIOScheduler, cadence: Cadence, delay: float | None = None) -> None:
    delay = cadence.next_delay_seconds() if delay is None else delay
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


BOOT_SCAN_DELAY_SECONDS = 45
RECENT_SCAN = timedelta(minutes=15)  # reinícios seguidos não viram rajada de consultas


def _first_delay_seconds(cadence: Cadence) -> float:
    """Varre logo após subir, a menos que já tenha varrido há pouco."""
    with SessionLocal() as session:
        last = session.scalar(select(func.max(HuntOffer.seen_at)))
    if last is not None:
        last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < RECENT_SCAN:
            return cadence.next_delay_seconds()
    return BOOT_SCAN_DELAY_SECONDS


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    backup_if_needed()
    scheduler.add_job(backup_if_needed, "interval", hours=6, id="backup")
    cadence = Cadence(parse_cycle(settings.scan_cycle_minutes))
    _schedule_next(scheduler, cadence, _first_delay_seconds(cadence))
    bot = await start_bot()
    yield
    await stop_bot(bot)
    scheduler.shutdown(wait=False)


app = FastAPI(title="precim", version="0.2.0", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Quem escreve (POST/PATCH/DELETE) precisa vir do próprio painel: um site qualquer aberto
    no navegador não pode mexer nas suas caças."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Origem não permitida"}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mascote": "🐷 de olho nas ofertas"}


class Painel(StaticFiles):
    """index.html sempre revalida (senão o navegador segue com o painel antigo após atualizar).
    Os arquivos em /assets têm hash no nome e podem ficar em cache."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if not path.startswith("assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


# Painel web (build do Vite). Precisa vir por último para não esconder /api e /health.
if FRONTEND_DIST.is_dir():
    app.mount("/", Painel(directory=FRONTEND_DIST, html=True), name="painel")
