"""Casos de uso compartilhados pela API e pelo bot do Telegram."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
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
from app.search_collector import scan_search
from app.stores.registry import store_for_url

MANUAL_HUNT_COOLDOWN = timedelta(minutes=5)  # respeita o anti-bot dos sites
_last_manual_hunt: datetime | None = None


class ServiceError(Exception):
    """Erro de regra de negócio com mensagem amigável."""


class CooldownError(ServiceError):
    def __init__(self, wait_seconds: int):
        super().__init__(f"Calma, caçador! Espere {wait_seconds}s para caçar de novo.")
        self.wait_seconds = wait_seconds


MAX_QUERIES_PER_WATCH = 4  # cada consulta extra é mais uma requisição ao site


def normalize_query(query: str) -> str:
    parts = [p.strip() for p in query.split("|") if p.strip()]
    if not parts:
        raise ServiceError("Informe o que caçar")
    if len(parts) > MAX_QUERIES_PER_WATCH:
        raise ServiceError(f"No máximo {MAX_QUERIES_PER_WATCH} buscas separadas por |")
    return " | ".join(parts)


def add_search(session: Session, *, query: str, min_capacity_gb: int | None = None,
               target_price: float | None = None, max_price_per_gb: float | None = None) -> SearchWatch:
    query = normalize_query(query)
    if target_price is None and max_price_per_gb is None:
        raise ServiceError("Informe uma meta: preço-alvo ou R$/GB máximo")
    watch = SearchWatch(query=query, min_capacity_gb=min_capacity_gb,
                        target_price=target_price, max_price_per_gb=max_price_per_gb)
    session.add(watch)
    session.commit()
    return watch


_EDITABLE = {"query", "min_capacity_gb", "target_price", "max_price_per_gb", "active"}


def update_search(session: Session, watch_id: int, **changes) -> tuple[SearchWatch, bool]:
    """Altera só os campos informados (None limpa uma meta). Retorna (caça, histórico_zerado).

    Trocar o termo é outra busca: zera ofertas vistas/avisadas. Mudar só metas mantém o histórico.
    """
    unknown = set(changes) - _EDITABLE
    if unknown:
        raise ServiceError(f"Campo não editável: {', '.join(sorted(unknown))}")
    watch = session.get(SearchWatch, watch_id)
    if not watch:
        raise ServiceError("Caça não encontrada")

    final = {f: getattr(watch, f) for f in _EDITABLE}
    final.update(changes)
    final["query"] = normalize_query(final["query"])
    if final["target_price"] is None and final["max_price_per_gb"] is None:
        raise ServiceError("A caça precisa de ao menos uma meta (preço-alvo ou R$/GB)")
    if final["min_capacity_gb"] is not None and final["min_capacity_gb"] < 0:
        raise ServiceError("Capacidade mínima inválida")

    reset = final["query"] != watch.query
    for field, value in final.items():
        setattr(watch, field, value)
    if reset:
        session.query(HuntOffer).filter_by(watch_id=watch_id).delete()
        session.query(SeenOffer).filter_by(watch_id=watch_id).delete()
    session.commit()
    return watch, reset


def remove_search(session: Session, watch_id: int) -> None:
    watch = session.get(SearchWatch, watch_id)
    if not watch:
        raise ServiceError("Caça não encontrada")
    session.query(HuntOffer).filter_by(watch_id=watch_id).delete()
    session.query(SeenOffer).filter_by(watch_id=watch_id).delete()
    session.delete(watch)
    session.commit()


async def add_tracked(session: Session, *, url: str, name: str, capacity_gb: int | None = None,
                      interface: str | None = None, target_price: float | None = None,
                      min_drop_pct: float | None = None,
                      max_price_per_gb: float | None = None) -> tuple[Listing, float | None]:
    store = store_for_url(url)
    if store is None:
        raise ServiceError("Loja ainda não suportada (hoje: Kabum)")
    if session.scalar(select(Listing).where(Listing.url == url)):
        raise ServiceError("Esse link já está sendo acompanhado")
    product = Product(name=name, capacity_gb=capacity_gb, interface=interface)
    listing = Listing(product=product, store=store.name, url=url)
    product.alerts.append(Alert(target_price=target_price, min_drop_pct=min_drop_pct,
                                max_price_per_gb=max_price_per_gb))
    session.add_all([product, listing])
    session.commit()
    snap = await scan_listing(session, listing)
    return listing, float(snap.price) if snap else None


def remove_tracked(session: Session, listing_id: int) -> None:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise ServiceError("Produto não encontrado")
    session.query(PriceSnapshot).filter_by(listing_id=listing_id).delete()
    product = listing.product
    session.delete(listing)
    session.flush()
    if not product.listings:
        for alert in list(product.alerts):
            session.delete(alert)
        session.delete(product)
    session.commit()


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


async def run_manual_hunt(session: Session) -> int:
    """Caça agora, com espera mínima entre chamadas manuais. Retorna alertas enviados."""
    global _last_manual_hunt
    now = datetime.now(timezone.utc)
    if _last_manual_hunt and now - _last_manual_hunt < MANUAL_HUNT_COOLDOWN:
        raise CooldownError(int((MANUAL_HUNT_COOLDOWN - (now - _last_manual_hunt)).total_seconds()))
    _last_manual_hunt = now
    sent = 0
    for watch in session.scalars(select(SearchWatch).where(SearchWatch.active.is_(True))).all():
        sent += await scan_search(session, watch)
    return sent
