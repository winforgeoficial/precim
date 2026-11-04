from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="ssd")
    capacity_gb: Mapped[int | None] = mapped_column(default=None)
    interface: Mapped[str | None] = mapped_column(String(20), default=None)  # nvme | sata
    listings: Mapped[list["Listing"]] = relationship(back_populates="product")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="product")


class Listing(Base):
    """Um produto em uma loja (uma URL monitorada)."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    store: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    product: Mapped[Product] = relationship(back_populates="listings")
    snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="listing")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    old_price: Mapped[float | None] = mapped_column(Numeric(12, 2), default=None)
    in_stock: Mapped[bool | None] = mapped_column(default=None)
    stock_qty: Mapped[int | None] = mapped_column(default=None)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    listing: Mapped[Listing] = relationship(back_populates="snapshots")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2), default=None)
    min_drop_pct: Mapped[float | None] = mapped_column(default=None)
    max_price_per_gb: Mapped[float | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(default=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    product: Mapped[Product] = relationship(back_populates="alerts")


class SearchWatch(Base):
    """Busca em agregador (ex.: "ssd nvme 1tb") com regras de alerta."""

    __tablename__ = "search_watches"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(200))
    min_capacity_gb: Mapped[int | None] = mapped_column(default=None)
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2), default=None)
    max_price_per_gb: Mapped[float | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(default=True)
    seen: Mapped[list["SeenOffer"]] = relationship(back_populates="watch")


class SeenOffer(Base):
    """Evita avisar de novo a mesma oferta (loja+produto) sem queda real de preço."""

    __tablename__ = "seen_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("search_watches.id"), index=True)
    key: Mapped[str] = mapped_column(String(400))
    last_notified_price: Mapped[float] = mapped_column(Numeric(12, 2))
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    watch: Mapped[SearchWatch] = relationship(back_populates="seen")


class HuntOffer(Base):
    """Ofertas da última varredura de uma busca (o painel lê daqui, sem bater no site)."""

    __tablename__ = "hunt_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("search_watches.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    merchant: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    capacity_gb: Mapped[int | None] = mapped_column(default=None)
    lowering_pct: Mapped[float] = mapped_column(default=0.0)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(20), default="buscape")  # buscape | kabum
    verified: Mapped[bool] = mapped_column(default=False)  # conferida direto na loja
    in_stock: Mapped[bool | None] = mapped_column(default=None)
    approximate: Mapped[bool] = mapped_column(default=False)  # preço pode ser de outra opção
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
