"""Amazon BR: lê a página de resultados de busca com um navegador comum (Playwright).

Sem disfarce: o navegador se apresenta normalmente, com poucas páginas e pausas longas.
Se a Amazon mostrar captcha/robô, o precim PARA por 12 h (não tenta contornar).
"""

import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.aggregators.buscape import Hit, parse_capacity_gb
from app.core.config import settings

log = logging.getLogger("precim.amazon")
SEARCH_URL = "https://www.amazon.com.br/s?k={q}"
PAGE_PAUSE_SECONDS = (8.0, 15.0)
BLOCK_COOLDOWN = timedelta(hours=12)
MAX_QUERIES_PER_CRAWL = 4

_blocked_until: datetime | None = None
_NOT_A_DRIVE = re.compile(
    r"adaptador|gabinete|enclosure|\bcase\b|caixa|suporte|dissipador|cabo|leitor|docking|"
    r"carca[cç]a|hub\b|\bgaveta", re.IGNORECASE)
_PRICE = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})")


class Blocked(Exception):
    """A Amazon pediu verificação (captcha/robô)."""


def is_blocked(html: str) -> bool:
    low = html.lower()
    return ("validatecaptcha" in low or "digite os caracteres" in low
            or "robot check" in low or "api-services-support@amazon" in low)


def parse_price(text: str | None) -> float | None:
    """'R$ 1.329,90' -> 1329.9 (o texto vem com &nbsp;)."""
    if not text:
        return None
    m = _PRICE.search(text.replace("\xa0", " "))
    return float(m.group(1).replace(".", "") + "." + m.group(2)) if m else None


def parse_search_html(html: str) -> list[Hit]:
    if is_blocked(html):
        raise Blocked("Amazon pediu verificação")
    hits: dict[str, Hit] = {}
    for node in HTMLParser(html).css('div[data-component-type="s-search-result"]'):
        asin = node.attributes.get("data-asin") or ""
        title_node = node.css_first("h2")
        price_node = node.css_first(".a-price:not(.a-text-price) .a-offscreen")
        if not asin or asin in hits or not title_node or not price_node:
            continue  # repetido (patrocinado + orgânico), sem título ou sem preço
        title = title_node.text(strip=True)
        price = parse_price(price_node.text())
        capacity = parse_capacity_gb(title)
        if (price is None or capacity is None or "ssd" not in title.lower()
                or _NOT_A_DRIVE.search(title)):
            continue
        list_node = node.css_first(".a-price.a-text-price .a-offscreen")
        list_price = parse_price(list_node.text()) if list_node else None
        hits[asin] = Hit(
            name=title, price=price, merchant="Amazon",
            url=f"https://www.amazon.com.br/dp/{asin}", capacity_gb=capacity,
            source="amazon", verified=True, in_stock=None,
            lowering_pct=(list_price - price) / list_price * 100
            if list_price and list_price > price else 0.0,
        )
    return list(hits.values())


def blocked_now() -> bool:
    return _blocked_until is not None and datetime.now(timezone.utc) < _blocked_until


async def search(queries: list[str]) -> list[Hit]:
    """Uma página por busca, em sequência, com pausas. Vazio se bloqueado."""
    global _blocked_until
    if blocked_now():
        log.info("Amazon em pausa por bloqueio até %s", _blocked_until)
        return []
    from playwright.async_api import async_playwright  # import tardio: só quem usa paga

    merged: dict[str, Hit] = {}
    launch: dict = {"headless": True}
    if settings.chromium_path:
        launch["executable_path"] = settings.chromium_path
    if hasattr(os, "geteuid") and os.geteuid() == 0:  # contêiner roda como root
        launch["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch)
        try:
            ctx = await browser.new_context(
                locale="pt-BR", timezone_id="America/Sao_Paulo",
                viewport={"width": 1366, "height": 850})
            page = await ctx.new_page()
            for i, q in enumerate(queries[:MAX_QUERIES_PER_CRAWL]):
                if i:
                    await asyncio.sleep(random.uniform(*PAGE_PAUSE_SECONDS))
                try:
                    await page.goto(SEARCH_URL.format(q=quote_plus(q)),
                                    wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(3000)
                    for hit in parse_search_html(await page.content()):
                        merged.setdefault(hit.url, hit)
                except Blocked:
                    _blocked_until = datetime.now(timezone.utc) + BLOCK_COOLDOWN
                    log.warning("Amazon pediu verificação: pausando a coleta por 12 h")
                    break
                except Exception:  # navegador/rede: só essa busca falha
                    log.exception("busca na Amazon falhou: %s", q)
        finally:
            await browser.close()
    return list(merged.values())
