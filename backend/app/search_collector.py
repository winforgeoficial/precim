"""Varre as buscas em agregadores e avisa só de ofertas novas ou com queda real."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregators import buscape
from app.alerts import price_per_gb, should_alert
from app.db.models import SearchWatch, SeenOffer
from app.notify.telegram import brl, send_telegram

log = logging.getLogger("precim.search")
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


async def scan_search(session: Session, watch: SearchWatch) -> int:
    try:
        hits = await buscape.search(watch.query)
    except Exception:
        log.exception("busca falhou: %s", watch.query)
        return 0

    sent = 0
    for hit in hits:
        if watch.min_capacity_gb and (hit.capacity_gb or 0) < watch.min_capacity_gb:
            continue
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
