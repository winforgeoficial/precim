"""Adapter da Kabum: lê o __NEXT_DATA__ da página de produto (sem navegador)."""

import json
import re

import httpx

from app.core.config import settings
from app.stores.base import Offer

_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


class ParseError(Exception):
    pass


def parse_product_html(html: str, url: str) -> Offer:
    m = _NEXT.search(html)
    if not m:
        raise ParseError("__NEXT_DATA__ ausente (layout mudou ou bloqueio)")
    try:
        product = json.loads(m.group(1))["props"]["pageProps"]["product"]
        prices = product["prices"]
    except (KeyError, ValueError) as exc:
        raise ParseError(f"estrutura inesperada: {exc!r}") from exc

    list_price = float(prices.get("price") or product.get("price") or 0)
    cash_price = float(prices.get("priceWithDiscount") or 0)
    old_price = float(prices.get("oldPrice") or 0)

    # Preço à vista (com desconto) é o que a Kabum cobra de fato quando existe.
    price = cash_price if cash_price > 0 else list_price
    if price <= 0:
        raise ParseError("preço zerado")
    reference = max(list_price, old_price)
    return Offer(
        price=price,
        old_price=reference if reference > price else None,
        in_stock=bool(product.get("available")),
        url=url,
        name=product.get("title"),
    )


class KabumStore:
    name = "kabum"

    async def fetch(self, url: str) -> Offer:
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=20
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return parse_product_html(resp.text, url)
