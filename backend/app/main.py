from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector import scan_all, scan_listing
from app.core.config import settings
from app.db.models import Alert, Listing, PriceSnapshot, Product
from app.db.session import SessionLocal, get_session, init_db
from app.stores.registry import store_for_url


def _db():
    with get_session() as session:
        yield session


async def _scheduled_scan() -> None:
    with SessionLocal() as session:
        await scan_all(session)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _scheduled_scan, "interval", minutes=settings.scan_interval_minutes, jitter=120,
        max_instances=1, coalesce=True,
    )
    scheduler.start()
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
