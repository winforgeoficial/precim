from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import price_per_gb, should_alert
from app.collector import scan_listing
from app.db.models import (
    Alert,
    HuntOffer,
    Listing,
    PriceSnapshot,
    Product,
    SearchWatch,
    SeenOffer,
)
from app.db.session import get_session
from app.gamification import Stats, achievements, level, xp
from app.search_collector import scan_search
from app.stores.registry import store_for_url

router = APIRouter(prefix="/api")
MANUAL_HUNT_COOLDOWN = timedelta(minutes=5)  # respeita o anti-bot dos sites
_last_manual_hunt: datetime | None = None


def get_db():
    with get_session() as session:
        yield session


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- produtos acompanhados por URL ----------

class WatchIn(BaseModel):
    url: HttpUrl
    name: str
    capacity_gb: int | None = None
    interface: str | None = None
    target_price: float | None = None
    min_drop_pct: float | None = None
    max_price_per_gb: float | None = None


@router.post("/watch", status_code=201)
async def add_watch(body: WatchIn, session: Session = Depends(get_db)) -> dict:
    url = str(body.url)
    store = store_for_url(url)
    if store is None:
        raise HTTPException(422, "Loja ainda não suportada (hoje: Kabum)")
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


@router.get("/watch")
def list_watch(session: Session = Depends(get_db)) -> list[dict]:
    out = []
    for listing in session.scalars(select(Listing).where(Listing.active.is_(True))).all():
        snaps = session.scalars(
            select(PriceSnapshot).where(PriceSnapshot.listing_id == listing.id)
            .order_by(PriceSnapshot.captured_at.desc()).limit(2)
        ).all()
        last = snaps[0] if snaps else None
        prev = snaps[1] if len(snaps) > 1 else None
        product = listing.product
        alert = product.alerts[0] if product.alerts else None
        out.append({
            "id": listing.id, "name": product.name, "store": listing.store, "url": listing.url,
            "capacity_gb": product.capacity_gb,
            "price": float(last.price) if last else None,
            "old_price": float(last.old_price) if last and last.old_price else None,
            "previous_price": float(prev.price) if prev else None,
            "price_per_gb": price_per_gb(float(last.price), product.capacity_gb) if last else None,
            "in_stock": last.in_stock if last else None,
            "target_price": float(alert.target_price) if alert and alert.target_price else None,
            "updated_at": last.captured_at.isoformat() if last else None,
        })
    return out


@router.delete("/watch/{listing_id}", status_code=204)
def delete_watch(listing_id: int, session: Session = Depends(get_db)) -> None:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Não encontrado")
    session.query(PriceSnapshot).filter_by(listing_id=listing_id).delete()
    product = listing.product
    session.delete(listing)
    session.flush()
    if not product.listings:
        for alert in list(product.alerts):
            session.delete(alert)
        session.delete(product)
    session.commit()


@router.get("/watch/{listing_id}/history")
def history(listing_id: int, session: Session = Depends(get_db)) -> list[dict]:
    if not session.get(Listing, listing_id):
        raise HTTPException(404, "Não encontrado")
    snaps = session.scalars(
        select(PriceSnapshot).where(PriceSnapshot.listing_id == listing_id)
        .order_by(PriceSnapshot.captured_at)
    ).all()
    return [{"at": s.captured_at.isoformat(), "price": float(s.price),
             "old_price": float(s.old_price) if s.old_price else None} for s in snaps]


# ---------- buscas em agregador ----------

class SearchIn(BaseModel):
    query: str
    min_capacity_gb: int | None = None
    target_price: float | None = None
    max_price_per_gb: float | None = None


@router.post("/search-watch", status_code=201)
def add_search_watch(body: SearchIn, session: Session = Depends(get_db)) -> dict:
    if not body.query.strip():
        raise HTTPException(422, "Informe o que caçar")
    if body.target_price is None and body.max_price_per_gb is None:
        raise HTTPException(422, "Informe target_price ou max_price_per_gb")
    watch = SearchWatch(**body.model_dump())
    session.add(watch)
    session.commit()
    return {"id": watch.id}


@router.get("/search-watch")
def list_search_watch(session: Session = Depends(get_db)) -> list[dict]:
    return [{
        "id": w.id, "query": w.query, "min_capacity_gb": w.min_capacity_gb,
        "target_price": float(w.target_price) if w.target_price is not None else None,
        "max_price_per_gb": w.max_price_per_gb, "active": w.active,
    } for w in session.scalars(select(SearchWatch)).all()]


@router.delete("/search-watch/{watch_id}", status_code=204)
def delete_search_watch(watch_id: int, session: Session = Depends(get_db)) -> None:
    watch = session.get(SearchWatch, watch_id)
    if not watch:
        raise HTTPException(404, "Não encontrado")
    session.query(HuntOffer).filter_by(watch_id=watch_id).delete()
    session.query(SeenOffer).filter_by(watch_id=watch_id).delete()
    session.delete(watch)
    session.commit()


# ---------- a caça ----------

def build_hunt(session: Session) -> list[dict]:
    rows: list[dict] = []
    for watch in session.scalars(select(SearchWatch).where(SearchWatch.active.is_(True))).all():
        for o in session.scalars(select(HuntOffer).where(HuntOffer.watch_id == watch.id)).all():
            price = float(o.price)
            rows.append({
                "name": o.name, "merchant": o.merchant, "price": price,
                "capacity_gb": o.capacity_gb, "price_per_gb": price_per_gb(price, o.capacity_gb),
                "lowering_pct": o.lowering_pct, "url": o.url, "query": watch.query,
                "seen_at": o.seen_at.isoformat(),
                "is_deal": should_alert(
                    price, capacity_gb=o.capacity_gb,
                    target_price=float(watch.target_price) if watch.target_price is not None
                    else None,
                    max_price_per_gb=watch.max_price_per_gb,
                ),
            })
    ppgs = sorted(r["price_per_gb"] for r in rows if r["price_per_gb"])
    for r in rows:
        if r["price_per_gb"] and len(ppgs) > 1:
            cheaper = sum(1 for p in ppgs if p < r["price_per_gb"])
            r["quality"] = round(100 * (1 - cheaper / (len(ppgs) - 1)))  # 100 = o mais barato
        else:
            r["quality"] = None
    rows.sort(key=lambda r: (not r["is_deal"], r["price_per_gb"] is None, r["price_per_gb"] or 0))
    return rows


@router.get("/hunt")
def hunt(session: Session = Depends(get_db)) -> dict:
    offers = build_hunt(session)
    last = session.scalar(select(func.max(HuntOffer.seen_at)))
    return {"offers": offers, "last_scan": last.isoformat() if last else None}


@router.post("/hunt/run")
async def hunt_run(session: Session = Depends(get_db)) -> dict:
    global _last_manual_hunt
    now = datetime.now(timezone.utc)
    if _last_manual_hunt and now - _last_manual_hunt < MANUAL_HUNT_COOLDOWN:
        wait = int((MANUAL_HUNT_COOLDOWN - (now - _last_manual_hunt)).total_seconds())
        raise HTTPException(429, f"Calma, caçador! Espere {wait}s para caçar de novo.")
    _last_manual_hunt = now
    sent = 0
    for watch in session.scalars(select(SearchWatch).where(SearchWatch.active.is_(True))).all():
        sent += await scan_search(session, watch)
    return {"alerts_sent": sent}


# ---------- mascote ----------

@router.get("/mascot")
def mascot(session: Session = Depends(get_db)) -> dict:
    snaps = session.scalar(select(func.count(PriceSnapshot.id))) or 0
    hunted = session.scalar(select(func.count(HuntOffer.id))) or 0
    alerts = session.scalar(select(func.count(SeenOffer.id))) or 0
    tracked = (session.scalar(select(func.count(Listing.id))) or 0) + (
        session.scalar(select(func.count(SearchWatch.id))) or 0)
    best_drop = 0.0
    for old, cur in session.execute(
        select(PriceSnapshot.old_price, PriceSnapshot.price).where(PriceSnapshot.old_price.isnot(None))
    ):
        if old and float(old) > 0:
            best_drop = max(best_drop, (float(old) - float(cur)) / float(old) * 100)
    stats = Stats(scans=snaps + hunted, alerts_sent=alerts, best_drop_pct=best_drop,
                  tracked=tracked)
    offers = build_hunt(session)
    if not offers:
        mood = "sleep" if tracked == 0 else "sniff"
    else:
        mood = "party" if any(o["is_deal"] for o in offers) else "sniff"
    return {**level(xp(stats)), "mood": mood, "achievements": achievements(stats),
            "stats": {"scans": stats.scans, "alerts_sent": alerts, "tracked": tracked}}
