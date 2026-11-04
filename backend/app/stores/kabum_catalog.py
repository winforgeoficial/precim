"""Descoberta de SSDs da Kabum pelo sitemap público e conferência direta de cada página."""

import asyncio
import logging
import random
import re
from dataclasses import dataclass

import httpx

from app.aggregators.buscape import Hit
from app.core.config import settings
from app.matching import matches_terms
from app.stores.kabum import KabumStore, ParseError

log = logging.getLogger("precim.kabum")
SITEMAP_URL = "https://www.kabum.com.br/sitemap/hardware.xml"
PAGE_PAUSE_SECONDS = (3.0, 6.0)  # educado com o site
MAX_PAGES_PER_CRAWL = 60

_LOC = re.compile(r"<loc>([^<]+)</loc>")
_SSD_SLUG = re.compile(r"/produto/\d+/(?:[a-z0-9-]*-)?ssd(?:-|$)")
_NOT_A_DRIVE = re.compile(
    r"storage|(?:^|-)nas(?:-|$)|gaveta|case|gabinete|adaptador|suporte|dissipador|cabo|"
    r"enclosure|docking|duplicador|leitor|kit-")
_CAP = re.compile(r"(?:^|-)(\d+)(tb|gb)(?:-|$)")


@dataclass(frozen=True)
class CatalogItem:
    url: str
    capacity_gb: int | None


def _slug(url: str) -> str:
    return url.split("/produto/", 1)[1] if "/produto/" in url else url


def slug_capacity_gb(url: str) -> int | None:
    found = []
    for m in _CAP.finditer(_slug(url)):
        v = int(m.group(1))
        found.append(v * 1000 if m.group(2) == "tb" else v)
    return max(found) if found else None


def discover(sitemap_xml: str) -> list[CatalogItem]:
    """SSDs (não NAS/gaveta/acessório) listados no sitemap."""
    items = []
    for url in _LOC.findall(sitemap_xml):
        if _SSD_SLUG.search(url) and not _NOT_A_DRIVE.search(_slug(url)):
            items.append(CatalogItem(url, slug_capacity_gb(url)))
    return items


def matches(item: CatalogItem, queries: list[str], min_capacity_gb: int | None) -> bool:
    """Capacidade mínima + termos não numéricos da busca (ex.: nvme) presentes no slug."""
    if min_capacity_gb and (item.capacity_gb or 0) < min_capacity_gb:
        return False
    return matches_terms(_slug(item.url), queries)


async def fetch_sitemap() -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=60
    ) as client:
        resp = await client.get(SITEMAP_URL)
        resp.raise_for_status()
    return resp.text


async def crawl(items: list[CatalogItem]) -> list[Hit]:
    """Confere cada página na loja, com pausas. Página que falha é ignorada."""
    store = KabumStore()
    hits: list[Hit] = []
    for i, item in enumerate(items[:MAX_PAGES_PER_CRAWL]):
        if i:
            await asyncio.sleep(random.uniform(*PAGE_PAUSE_SECONDS))
        try:
            offer = await store.fetch(item.url)
        except (httpx.HTTPError, ParseError):
            log.warning("página da Kabum falhou: %s", item.url)
            continue
        hits.append(Hit(
            name=offer.name or _slug(item.url), price=offer.price, merchant="KaBuM!",
            url=item.url, capacity_gb=item.capacity_gb, source="kabum", verified=True,
            in_stock=offer.in_stock,
            lowering_pct=((offer.old_price - offer.price) / offer.old_price * 100)
            if offer.old_price else 0.0,
        ))
    return hits
