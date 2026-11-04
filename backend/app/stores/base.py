from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class Offer:
    price: float
    url: str
    old_price: float | None = None
    in_stock: bool | None = None
    stock_qty: int | None = None
    name: str | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Store(Protocol):
    """Contrato único de todo adapter de loja."""

    name: str

    async def fetch(self, url: str) -> Offer: ...
