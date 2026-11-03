import httpx

from app.core.config import settings


def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_alert(name: str, store: str, price: float, old_price: float | None,
                 in_stock: bool | None, ppg: float | None, url: str) -> str:
    lines = ["🐷 Achei uma oferta!", f"<b>{name}</b>", f"🏪 {store}"]
    price_line = f"💰 {brl(price)}"
    if old_price and old_price > price:
        pct = (old_price - price) / old_price * 100
        price_line += f" (era {brl(old_price)}, -{pct:.0f}%)"
    lines.append(price_line)
    if ppg:
        lines.append(f"📏 {brl(ppg)}/GB")
    if in_stock is not None:
        lines.append("📦 Em estoque" if in_stock else "⛔ Sem estoque")
    lines.append(url)
    return "\n".join(lines)


async def send_telegram(text: str) -> bool:
    """Retorna False (sem erro) se o bot não estiver configurado."""
    if not settings.telegram_token or not settings.telegram_chat_id:
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML"},
        )
        resp.raise_for_status()
    return True
