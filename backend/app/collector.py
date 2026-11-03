"""Coleta de um anúncio: busca a oferta, grava o histórico e dispara alertas."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import price_per_gb, should_alert
from app.db.models import Listing, PriceSnapshot
from app.notify.telegram import format_alert, send_telegram
from app.stores.registry import store_for_url

log = logging.getLogger("precim.collector")
ALERT_COOLDOWN = timedelta(hours=12)


async def scan_listing(session: Session, listing: Listing) -> PriceSnapshot | None:
    store = store_for_url(listing.url)
    if store is None:
        log.warning("sem adapter para %s", listing.url)
        return None

    previous = session.scalar(
        select(PriceSnapshot)
        .where(PriceSnapshot.listing_id == listing.id)
        .order_by(PriceSnapshot.captured_at.desc())
        .limit(1)
    )
    try:
        offer = await store.fetch(listing.url)
    except Exception:  # loja fora do ar/layout mudou: segue com as demais
        log.exception("falha ao coletar %s", listing.url)
        return None

    snap = PriceSnapshot(
        listing_id=listing.id,
        price=offer.price,
        old_price=offer.old_price,
        in_stock=offer.in_stock,
        stock_qty=offer.stock_qty,
    )
    session.add(snap)

    product = listing.product
    now = datetime.now(timezone.utc)
    for alert in product.alerts:
        if not alert.active or offer.in_stock is False:
            continue
        if alert.last_notified_at and now - _aware(alert.last_notified_at) < ALERT_COOLDOWN:
            continue
        if should_alert(
            offer.price,
            previous_price=float(previous.price) if previous else None,
            capacity_gb=product.capacity_gb,
            target_price=float(alert.target_price) if alert.target_price is not None else None,
            min_drop_pct=alert.min_drop_pct,
            max_price_per_gb=alert.max_price_per_gb,
        ):
            text = format_alert(
                product.name, listing.store, offer.price, offer.old_price, offer.in_stock,
                price_per_gb(offer.price, product.capacity_gb), listing.url,
            )
            try:
                if await send_telegram(text):
                    alert.last_notified_at = now
            except Exception:
                log.exception("falha ao enviar Telegram")
    session.commit()
    return snap


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def scan_all(session: Session) -> int:
    listings = session.scalars(select(Listing).where(Listing.active.is_(True))).all()
    done = 0
    for listing in listings:
        if await scan_listing(session, listing):
            done += 1
    return done
