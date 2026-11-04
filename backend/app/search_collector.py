"""Varre as buscas em agregadores e avisa só de ofertas novas ou com queda real."""

import asyncio
import logging
import random

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.aggregators import buscape
from app.alerts import price_per_gb, should_alert
from app.db.models import HuntOffer, SearchWatch, SeenOffer
from app.notify.telegram import brl, send_telegram

log = logging.getLogger("precim.search")
QUERY_PAUSE_SECONDS = (3.0, 6.0)  # pausa entre consultas da mesma caça (anti-bot)
MIN_REDROP_PCT = 3.0  # só re-avisa a mesma oferta se cair ao menos isso


def format_hit(hit: buscape.Hit) -> str:
    lines = ["🐷 Achei uma oferta!", f"<b>{hit.name}</b>", f"🏪 {hit.merchant}",
             f"💰 {brl(hit.price)}"]
    ppg = price_per_gb(hit.price, hit.capacity_gb)
    if ppg:
        lines.append(f"📏 {brl(ppg)}/GB")
    if hit.lowering_pct:
        lines.append(f"📉 -{hit.lowering_pct:.0f}% no histórico")
    lines.append(hit.url)
    return "\n".join(lines)


def split_queries(query: str) -> list[str]:
    return [q.strip() for q in query.split("|") if q.strip()]


async def _collect(query: str) -> list[buscape.Hit] | None:
    """Roda cada consulta ("a | b | c"), junta e remove repetidos. None se todas falharem."""
    merged: dict[tuple[str, float], buscape.Hit] = {}
    ok = False
    for i, q in enumerate(split_queries(query)):
        if i:
            await asyncio.sleep(random.uniform(*QUERY_PAUSE_SECONDS))
        try:
            for hit in await buscape.search(q):
                merged.setdefault((hit.key, hit.price), hit)
            ok = True
        except Exception:
            log.exception("busca falhou: %s", q)
    return list(merged.values()) if ok else None


async def scan_search(session: Session, watch: SearchWatch) -> int:
    hits = await _collect(watch.query)
    if hits is None:
        return 0

    hits = [
        h for h in hits
        if not watch.min_capacity_gb or (h.capacity_gb or 0) >= watch.min_capacity_gb
    ]
    session.execute(delete(HuntOffer).where(HuntOffer.watch_id == watch.id))
    session.add_all(
        HuntOffer(
            watch_id=watch.id, name=h.name, merchant=h.merchant, price=h.price,
            capacity_gb=h.capacity_gb, lowering_pct=h.lowering_pct, url=h.url,
        )
        for h in hits
    )

    sent = 0
    for hit in hits:
        if not should_alert(
            hit.price,
            capacity_gb=hit.capacity_gb,
            target_price=float(watch.target_price) if watch.target_price is not None else None,
            max_price_per_gb=watch.max_price_per_gb,
        ):
            continue
        seen = session.scalar(
            select(SeenOffer).where(SeenOffer.watch_id == watch.id, SeenOffer.key == hit.key)
        )
        if seen:
            last = float(seen.last_notified_price)
            if (last - hit.price) / last * 100 < MIN_REDROP_PCT:
                continue
        try:
            if not await send_telegram(format_hit(hit)):
                continue
        except Exception:
            log.exception("falha ao enviar Telegram")
            continue
        if seen:
            seen.last_notified_price = hit.price
        else:
            session.add(SeenOffer(watch_id=watch.id, key=hit.key, last_notified_price=hit.price))
        sent += 1
    session.commit()
    return sent


async def scan_all_searches(session: Session) -> int:
    watches = session.scalars(select(SearchWatch).where(SearchWatch.active.is_(True))).all()
    return sum([await scan_search(session, w) for w in watches])
