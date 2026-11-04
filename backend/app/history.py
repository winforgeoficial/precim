"""Histórico de preços das ofertas: guarda só mudanças (e um ponto a cada 12 h)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.aggregators.buscape import Hit
from app.db.models import OfferPrice

HEARTBEAT = timedelta(hours=12)  # mesmo sem mudar, anota de tempos em tempos
KEEP = timedelta(days=90)
FAKE_MIN_DAYS = 2  # histórico curto demais para julgar desconto
FAKE_MIN_PCT = 10.0


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record(session: Session, watch_id: int, hits: list[Hit]) -> None:
    now = datetime.now(timezone.utc)
    last: dict[str, float] = {}
    rows = session.execute(
        select(OfferPrice.key, OfferPrice.price).where(
            OfferPrice.watch_id == watch_id, OfferPrice.captured_at >= now - HEARTBEAT,
        ).order_by(OfferPrice.captured_at)
    )
    for key, price in rows:
        last[key] = float(price)
    for h in hits:
        if last.get(h.key) != h.price:
            session.add(OfferPrice(watch_id=watch_id, key=h.key, price=h.price, captured_at=now))
            last[h.key] = h.price
    session.execute(delete(OfferPrice).where(OfferPrice.captured_at < now - KEEP))
    session.flush()


@dataclass(frozen=True)
class Stats:
    low: float
    high: float
    points: int
    days: float


def stats(session: Session, watch_id: int) -> dict[str, Stats]:
    rows = session.execute(
        select(OfferPrice.key, func.min(OfferPrice.price), func.max(OfferPrice.price),
               func.count(OfferPrice.id), func.min(OfferPrice.captured_at),
               func.max(OfferPrice.captured_at))
        .where(OfferPrice.watch_id == watch_id).group_by(OfferPrice.key)
    )
    return {
        key: Stats(float(lo), float(hi), n, (_utc(last) - _utc(first)).total_seconds() / 86400)
        for key, lo, hi, n, first, last in rows
    }


def is_lowest(price: float, st: Stats | None) -> bool:
    """Menor preço já visto (só vale com histórico que já variou)."""
    return bool(st and st.points >= 2 and st.high > st.low and price <= st.low)


def fake_discount(price: float, lowering_pct: float, st: Stats | None) -> bool:
    """O "de/por" da loja não bate com o que vimos: o preço 'antigo' nunca existiu aqui."""
    if not st or lowering_pct < FAKE_MIN_PCT or st.days < FAKE_MIN_DAYS or lowering_pct >= 100:
        return False
    claimed_old = price / (1 - lowering_pct / 100)
    return st.high < claimed_old * 0.9


def series(session: Session, watch_id: int, key: str) -> list[dict]:
    rows = session.execute(
        select(OfferPrice.captured_at, OfferPrice.price)
        .where(OfferPrice.watch_id == watch_id, OfferPrice.key == key)
        .order_by(OfferPrice.captured_at)
    )
    return [{"at": _utc(at), "price": float(p)} for at, p in rows]
