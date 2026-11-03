import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cadence import Cadence, parse_cycle
from app.collector import scan_all, scan_listing
from app.core.config import settings
from app.db.models import Alert, Listing, PriceSnapshot, Product, SearchWatch
from app.db.session import SessionLocal, get_session, init_db
from app.search_collector import scan_all_searches
from app.stores.registry import store_for_url

log = logging.getLogger("precim")


def _db():
    with get_session() as session:
        yield session


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


app = FastAPI(title="precim", version="0.1.0", lifespan=lifespan)


class WatchIn(BaseModel):
    url: HttpUrl
    name: str
    capacity_gb: int | None = None
    interface: str | None = None
    target_price: float | None = None
    min_drop_pct: float | None = None
    max_price_per_gb: float | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mascote": "🐷 de olho nas ofertas"}


@app.post("/watch", status_code=201)
async def watch(body: WatchIn, session: Session = Depends(_db)) -> dict:
    url = str(body.url)
    store = store_for_url(url)
    if store is None:
        raise HTTPException(422, "Loja ainda não suportada")
    if session.scalar(select(Listing).where(Listing.url == url)):
        raise HTTPException(409, "URL já está sendo acompanhada")
    product = Product(name=body.name, capacity_gb=body.capacity_gb, interface=body.interface)
    listing = Listing(product=product, store=store.name, url=url)
    product.alerts.append(Alert(
        target_price=body.target_price, min_drop_pct=body.min_drop_pct,
        max_price_per_gb=body.max_price_per_gb,
    ))
    session.add_all([product, listing])
    session.commit()
    snap = await scan_listing(session, listing)
    return {"listing_id": listing.id, "price": float(snap.price) if snap else None}


@app.get("/watch")
def list_watch(session: Session = Depends(_db)) -> list[dict]:
    out = []
    for listing in session.scalars(select(Listing)).all():
        last = session.scalar(
            select(PriceSnapshot).where(PriceSnapshot.listing_id == listing.id)
            .order_by(PriceSnapshot.captured_at.desc()).limit(1)
        )
        out.append({
            "id": listing.id, "name": listing.product.name, "store": listing.store,
            "url": listing.url,
            "price": float(last.price) if last else None,
            "old_price": float(last.old_price) if last and last.old_price else None,
            "in_stock": last.in_stock if last else None,
        })
    return out


class SearchIn(BaseModel):
    query: str
    min_capacity_gb: int | None = None
    target_price: float | None = None
    max_price_per_gb: float | None = None


@app.post("/search-watch", status_code=201)
def add_search_watch(body: SearchIn, session: Session = Depends(_db)) -> dict:
    if body.target_price is None and body.max_price_per_gb is None:
        raise HTTPException(422, "Informe target_price ou max_price_per_gb")
    watch = SearchWatch(**body.model_dump())
    session.add(watch)
    session.commit()
    return {"id": watch.id}
