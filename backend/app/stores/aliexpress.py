"""AliExpress: lê a busca renderizada com um navegador comum (Playwright).

O preço do card é o da opção MAIS BARATA do anúncio (variações de capacidade/cor), por isso
toda oferta sai marcada como `approximate`. Para não fingir um SSD de 1TB barato, anúncios com
várias capacidades no título ("500GB 1TB 2TB") contam pela MENOR capacidade.
Captcha/verificação => pausa de 12 h, sem tentar contornar.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.aggregators.buscape import Hit, all_capacities_gb
from app.browser import Page, render_pages

log = logging.getLogger("precim.aliexpress")
SEARCH_URL = "https://pt.aliexpress.com/w/wholesale-{q}.html"
PAGE_PAUSE_SECONDS = (8.0, 15.0)
BLOCK_COOLDOWN = timedelta(hours=12)
MAX_QUERIES_PER_CRAWL = 3

_blocked_until: datetime | None = None
_ITEM = re.compile(r"/item/(\d+)\.html")
_MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?")
_NOT_A_DRIVE = re.compile(
    r"adaptador|gabinete|enclosure|\bcase\b|caixa|suporte|dissipador|cabo|leitor|docking|"
    r"carca[cç]a|\bhub\b|gaveta|heatsink|resfriador|cart[ãa]o de expans[ãa]o", re.IGNORECASE)


class Blocked(Exception):
    """O AliExpress pediu verificação (captcha/deslizar)."""


def is_blocked(page: Page) -> bool:
    low = page.html.lower()
    return ("captcha" in page.title.lower() or "punish" in page.final_url
            or "x5secdata" in page.final_url or 'id="nocaptcha"' in low)


def money_values(text: str) -> list[float]:
    """Todos os 'R$ ...' do texto do card, na ordem: 'R$1.222,17', 'R$268', 'R$312,8'."""
    out = []
    for m in _MONEY.finditer(text.replace("\xa0", " ")):
        cents = (m.group(2) or "0").ljust(2, "0")
        out.append(float(m.group(1).replace(".", "") + "." + cents))
    return out


def parse_search_html(html: str) -> list[Hit]:
    hits: dict[str, Hit] = {}
    for a in HTMLParser(html).css('a[href*="/item/"]'):
        m = _ITEM.search(a.attributes.get("href") or "")
        if not m or m.group(1) in hits:
            continue
        parts = [p for p in a.text(separator="\n", strip=True).split("\n") if p.strip()]
        if not parts:
            continue
        title = parts[0]
        prices = money_values(" ".join(parts[1:]))
        caps = all_capacities_gb(title, short_units=True)  # "128G", "2T" também valem
        if (not prices or not caps or "ssd" not in title.lower()
                or _NOT_A_DRIVE.search(title)):
            continue
        price = prices[0]  # o 1º valor do card é o preço atual
        list_price = next((v for v in prices[1:] if v > price), None)
        hits[m.group(1)] = Hit(
            name=title, price=price, merchant="AliExpress",
            url=f"https://pt.aliexpress.com/item/{m.group(1)}.html",
            capacity_gb=min(caps),  # várias capacidades no título: o preço é da menor
            source="aliexpress", verified=True, approximate=True, in_stock=None,
            lowering_pct=(list_price - price) / list_price * 100 if list_price else 0.0,
        )
    return list(hits.values())


def blocked_now() -> bool:
    return _blocked_until is not None and datetime.now(timezone.utc) < _blocked_until


async def search(queries: list[str]) -> list[Hit]:
    """Uma página por busca, com pausas e rolagem leve. Vazio se bloqueado."""
    global _blocked_until
    if blocked_now():
        log.info("AliExpress em pausa por bloqueio até %s", _blocked_until)
        return []
    urls = [SEARCH_URL.format(q=quote(q.strip().replace(" ", "-")))
            for q in queries[:MAX_QUERIES_PER_CRAWL]]
    pages, was_blocked = await render_pages(
        urls, pause=PAGE_PAUSE_SECONDS, blocked=is_blocked, scroll=True, settle_ms=5000)
    if was_blocked:
        _blocked_until = datetime.now(timezone.utc) + BLOCK_COOLDOWN
        log.warning("AliExpress pediu verificação: pausando a coleta por 12 h")
    merged: dict[str, Hit] = {}
    for pg in pages:
        for hit in parse_search_html(pg.html):
            merged.setdefault(hit.url, hit)
    return list(merged.values())
