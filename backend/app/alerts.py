"""Regras puras de alerta — sem I/O, fáceis de testar."""


def price_per_gb(price: float, capacity_gb: int | None) -> float | None:
    if not capacity_gb:
        return None
    return round(price / capacity_gb, 4)


def should_alert(
    price: float,
    *,
    previous_price: float | None = None,
    capacity_gb: int | None = None,
    target_price: float | None = None,
    min_drop_pct: float | None = None,
    max_price_per_gb: float | None = None,
) -> bool:
    """Dispara se QUALQUER regra configurada for satisfeita."""
    if target_price is not None and price <= target_price:
        return True
    if min_drop_pct is not None and previous_price and previous_price > 0:
        drop = (previous_price - price) / previous_price * 100
        if drop >= min_drop_pct:
            return True
    if max_price_per_gb is not None:
        ppg = price_per_gb(price, capacity_gb)
        if ppg is not None and ppg <= max_price_per_gb:
            return True
    return False
