from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.alerts import price_per_gb
from app.db.models import (
    HuntOffer,
    Listing,
    PriceSnapshot,
    SearchWatch,
    SeenOffer,
)
from app.db.session import get_session
from app.gamification import Stats, achievements, level, xp

router = APIRouter(prefix="/api")


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
    try:
        listing, price = await services.add_tracked(
            session, url=str(body.url), name=body.name, capacity_gb=body.capacity_gb,
            interface=body.interface, target_price=body.target_price,
            min_drop_pct=body.min_drop_pct, max_price_per_gb=body.max_price_per_gb)
    except services.ServiceError as exc:
        raise HTTPException(409 if "já está" in str(exc) else 422, str(exc)) from exc
    return {"listing_id": listing.id, "price": price}


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
    try:
        services.remove_tracked(session, listing_id)
    except services.ServiceError as exc:
        raise HTTPException(404, str(exc)) from exc


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
    try:
        watch = services.add_search(session, **body.model_dump())
    except services.ServiceError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": watch.id}


def _search_dict(w: SearchWatch) -> dict:
    return {
        "id": w.id, "query": w.query, "min_capacity_gb": w.min_capacity_gb,
        "target_price": float(w.target_price) if w.target_price is not None else None,
        "max_price_per_gb": w.max_price_per_gb, "active": w.active,
    }


@router.get("/search-watch")
def list_search_watch(session: Session = Depends(get_db)) -> list[dict]:
    return [_search_dict(w) for w in session.scalars(select(SearchWatch)).all()]


class SearchPatch(BaseModel):
    query: str | None = None
    min_capacity_gb: int | None = None
    target_price: float | None = None
    max_price_per_gb: float | None = None
    active: bool | None = None


@router.patch("/search-watch/{watch_id}")
def patch_search_watch(watch_id: int, body: SearchPatch, session: Session = Depends(get_db)) -> dict:
    """Só altera o que veio no corpo; enviar null limpa a meta/capacidade."""
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if changes.get("query") is None:
        changes.pop("query", None)
    if changes.get("active") is None:
        changes.pop("active", None)
    try:
        watch, reset = services.update_search(session, watch_id, **changes)
    except services.ServiceError as exc:
        raise HTTPException(404 if "não encontrada" in str(exc) else 422, str(exc)) from exc
    return {**_search_dict(watch), "history_reset": reset}


@router.delete("/search-watch/{watch_id}", status_code=204)
def delete_search_watch(watch_id: int, session: Session = Depends(get_db)) -> None:
    try:
        services.remove_search(session, watch_id)
    except services.ServiceError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------- a caça ----------

@router.get("/hunt")
def hunt(session: Session = Depends(get_db)) -> dict:
    offers = services.build_hunt(session)
    last = session.scalar(select(func.max(HuntOffer.seen_at)))
    return {"offers": offers, "last_scan": last.isoformat() if last else None}


@router.post("/hunt/run")
async def hunt_run(session: Session = Depends(get_db)) -> dict:
    try:
        return {"alerts_sent": await services.run_manual_hunt(session)}
    except services.CooldownError as exc:
        raise HTTPException(429, str(exc)) from exc


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
    offers = services.build_hunt(session)
    if not offers:
        mood = "sleep" if tracked == 0 else "sniff"
    else:
        mood = "party" if any(o["is_deal"] for o in offers) else "sniff"
    return {**level(xp(stats)), "mood": mood, "achievements": achievements(stats),
            "stats": {"scans": stats.scans, "alerts_sent": alerts, "tracked": tracked}}
