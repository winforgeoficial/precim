"""Busca no Buscapé/Zoom (mesmo grupo e mesmos dados): lê o estado Redux do __NEXT_DATA__."""

import json
import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from app.core.config import settings

_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
# número + unidade; aceita "1.000GB" (milhar), "1,5TB"; ignora "GB/s" e colados em outras palavras
_CAPACITY = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(tb|gb)(?![\w/])", re.IGNORECASE)
_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+")
MIN_PLAUSIBLE_GB, MAX_PLAUSIBLE_GB = 16, 100_000
HOSTS = ("https://www.buscape.com.br", "https://www.zoom.com.br")  # reserva: Zoom


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class Hit:
    name: str
    price: float
    merchant: str  # "vários (N lojas)" quando é página de produto agregada
    url: str
    capacity_gb: int | None
    lowering_pct: float = 0.0
    source: str = "buscape"
    verified: bool = False  # True só quando conferida direto na loja
    in_stock: bool | None = None

    @property
    def key(self) -> str:
        return f"{self.merchant}|{self.name}".lower()


def parse_capacity_gb(name: str) -> int | None:
    """Maior capacidade plausível citada no título (1TB = 1000 GB; "1.000GB 1TB" = 1000)."""
    found: list[int] = []
    for m in _CAPACITY.finditer(name):
        raw = m.group(1)
        value = float(raw.replace(".", "")) if _THOUSANDS.fullmatch(raw) else float(
            raw.replace(",", "."))
        gb = int(value * 1000) if m.group(2).lower() == "tb" else int(value)
        if MIN_PLAUSIBLE_GB <= gb <= MAX_PLAUSIBLE_GB:
            found.append(gb)
    return max(found) if found else None


def parse_search_html(html: str, host: str = HOSTS[0]) -> list[Hit]:
    m = _NEXT.search(html)
    if not m:
        raise ParseError("__NEXT_DATA__ ausente (layout mudou ou bloqueio)")
    try:
        raw = json.loads(m.group(1))["props"]["initialReduxState"]["hits"]["hits"]
    except (KeyError, ValueError) as exc:
        raise ParseError(f"estrutura inesperada: {exc!r}") from exc

    hits: list[Hit] = []
    for item in raw:
        name, price = item.get("name"), item.get("price")
        if not name or not price or "ssd" not in name.lower():
            continue
        merchant = item.get("merchantName")
        if not merchant:
            count = item.get("storeCount") or 0
            plural = "loja" if count == 1 else "lojas"
            merchant = f"vários ({count} {plural})" if count else "vários"
        hits.append(Hit(
            name=name,
            price=float(price),
            merchant=merchant,
            url=host + (item.get("url") or ""),
            capacity_gb=parse_capacity_gb(name),
            lowering_pct=float(item.get("loweringPercentage") or 0),
        ))
    return hits


async def search(query: str) -> list[Hit]:
    """Tenta o Buscapé; se falhar, usa o Zoom."""
    last_exc: Exception | None = None
    for host in HOSTS:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=25
            ) as client:
                resp = await client.get(f"{host}/search?q={quote_plus(query)}")
                resp.raise_for_status()
            return parse_search_html(resp.text, host)
        except (httpx.HTTPError, ParseError) as exc:
            last_exc = exc
    raise RuntimeError(f"Buscapé e Zoom falharam: {last_exc!r}")
