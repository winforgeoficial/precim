"""Varre as buscas e avisa só de ofertas novas ou com queda real.

Duas fontes:
- Buscapé/Zoom (agregador): rápido e amplo, mas a oferta pode já não existir na loja.
- Kabum direto (sitemap + página do produto): confere preço e estoque na própria loja.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.aggregators import buscape
from app.alerts import price_per_gb, should_alert
from app.core.config import settings
from app.db.models import HuntOffer, SearchWatch, SeenOffer
from app.matching import matches_terms
from app.notify.telegram import brl, send_telegram
from app.stores import aliexpress, amazon, kabum_catalog

log = logging.getLogger("precim.search")
QUERY_PAUSE_SECONDS = (3.0, 6.0)  # pausa entre consultas da mesma caça (anti-bot)
MAX_ALERTS_PER_SCAN = 5  # evita enxurrada no grupo; o resto sai nas próximas varreduras
MIN_REDROP_PCT = 3.0  # só re-avisa a mesma oferta se cair ao menos isso
DIRECT_INTERVAL = timedelta(hours=3)  # coletas diretas são mais pesadas: não rodam a cada varredura
DUE_SLACK = timedelta(minutes=15)  # varreduras horárias têm jitter; sem folga a coleta pularia p/ 4 h

VERIFIED_NOTE = "✅ Conferida direto na loja"
APPROXIMATE_NOTE = (
    "⚠️ Preço aproximado: o AliExpress mostra o valor da opção mais barata do anúncio. "
    "Desconfie de marcas desconhecidas: SSD com capacidade falsificada é comum."
)


def format_hit(hit: buscape.Hit) -> str:
    lines = ["🐷 Achei uma oferta!", f"<b>{hit.name}</b>", f"🏪 {hit.merchant}",
             f"💰 {brl(hit.price)}"]
    ppg = price_per_gb(hit.price, hit.capacity_gb)
    if ppg:
        lines.append(f"📏 {brl(ppg)}/GB")
    if hit.lowering_pct:
        lines.append(f"📉 -{hit.lowering_pct:.0f}% de desconto")
    if hit.in_stock is not None:
        lines.append("📦 Em estoque" if hit.in_stock else "⛔ Sem estoque")
    lines.append(VERIFIED_NOTE)  # só ofertas conferidas chegam ao Telegram
    if hit.approximate:
        lines.append(APPROXIMATE_NOTE)
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


async def _store_and_alert(session: Session, watch: SearchWatch, source: str,
                           hits: list[buscape.Hit]) -> int:
    """Troca as ofertas dessa fonte para a caça e avisa as que merecem."""
    session.execute(delete(HuntOffer).where(
        HuntOffer.watch_id == watch.id, HuntOffer.source == source))
    session.add_all(
        HuntOffer(
            watch_id=watch.id, name=h.name, merchant=h.merchant, price=h.price,
            capacity_gb=h.capacity_gb, lowering_pct=h.lowering_pct, url=h.url,
            source=h.source, verified=h.verified, in_stock=h.in_stock,
            approximate=h.approximate,
        )
        for h in hits
    )

    sent = 0
    # melhores R$/GB primeiro: se houver limite, vão ao grupo as mais interessantes
    for hit in sorted(hits, key=lambda h: (price_per_gb(h.price, h.capacity_gb) is None,
                                           price_per_gb(h.price, h.capacity_gb) or 0)):
        if sent >= MAX_ALERTS_PER_SCAN:
            break
        if not hit.verified:  # Buscapé/Zoom: só aparece no painel, nunca vai ao grupo
            continue
        if hit.in_stock is False:  # sem estoque confirmado: lista, mas não avisa
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


async def scan_search(session: Session, watch: SearchWatch) -> int:
    """Fonte 1: agregador (Buscapé/Zoom). Ofertas ficam marcadas como não verificadas."""
    hits = await _collect(watch.query)
    if hits is None:
        return 0
    hits = [
        h for h in hits
        if not watch.min_capacity_gb or (h.capacity_gb or 0) >= watch.min_capacity_gb
    ]
    return await _store_and_alert(session, watch, "buscape", hits)


def _direct_is_due(session: Session, watch: SearchWatch, source: str = "kabum") -> bool:
    last = session.scalar(select(func.max(HuntOffer.seen_at)).where(
        HuntOffer.watch_id == watch.id, HuntOffer.source == source))
    if last is None:
        return True
    last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last >= DIRECT_INTERVAL - DUE_SLACK


async def scan_direct_kabum(session: Session, watch: SearchWatch, force: bool = False) -> int:
    """Fonte 2: confere os SSDs da Kabum direto na loja (a cada 3 h, ou com force)."""
    if not force and not _direct_is_due(session, watch):
        return 0
    try:
        items = kabum_catalog.discover(await kabum_catalog.fetch_sitemap())
    except Exception:
        log.exception("sitemap da Kabum falhou")
        return 0
    wanted = [i for i in items
              if kabum_catalog.matches(i, split_queries(watch.query), watch.min_capacity_gb)]
    log.info("Kabum direto: %d candidatos para “%s”", len(wanted), watch.query)
    if not wanted:
        session.execute(delete(HuntOffer).where(
            HuntOffer.watch_id == watch.id, HuntOffer.source == "kabum"))
        session.commit()
        return 0
    hits = await kabum_catalog.crawl(wanted)
    if not hits:  # tudo falhou: mantém o que já havia
        return 0
    return await _store_and_alert(session, watch, "kabum", hits)


async def _scan_browser_source(session: Session, watch: SearchWatch, source: str, module,
                               enabled: bool, force: bool) -> int:
    """Fontes lidas por navegador (Amazon, AliExpress): a cada 3 h, ou com force."""
    if not enabled or module.blocked_now():
        return 0
    if not force and not _direct_is_due(session, watch, source):
        return 0
    queries = split_queries(watch.query)
    try:
        hits = await module.search(queries)
    except Exception:
        log.exception("coleta de %s falhou", source)
        return 0
    hits = [h for h in hits
            if (not watch.min_capacity_gb or (h.capacity_gb or 0) >= watch.min_capacity_gb)
            and matches_terms(h.name, queries)]
    if not hits:  # bloqueio ou nada relevante: não apaga o que já havia
        return 0
    return await _store_and_alert(session, watch, source, hits)


async def scan_direct_amazon(session: Session, watch: SearchWatch, force: bool = False) -> int:
    """Fonte 3: busca da Amazon lida com navegador."""
    return await _scan_browser_source(
        session, watch, "amazon", amazon, settings.amazon_enabled, force)


async def scan_direct_aliexpress(session: Session, watch: SearchWatch, force: bool = False) -> int:
    """Fonte 4: busca do AliExpress lida com navegador (preço aproximado)."""
    return await _scan_browser_source(
        session, watch, "aliexpress", aliexpress, settings.aliexpress_enabled, force)


async def scan_all_searches(session: Session) -> int:
    watches = session.scalars(select(SearchWatch).where(SearchWatch.active.is_(True))).all()
    sent = 0
    for w in watches:
        sent += await scan_search(session, w)
        sent += await scan_direct_kabum(session, w)
        sent += await scan_direct_amazon(session, w)
        sent += await scan_direct_aliexpress(session, w)
    return sent
