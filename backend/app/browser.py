"""Navegador comum (Playwright) para ler páginas de lojas que não têm API.

Sem disfarce: o navegador se apresenta normalmente. Poucas páginas, pausas longas, e quem
pedir verificação (captcha/robô) interrompe a coleta; o chamador decide a pausa.
"""

import asyncio
import logging
import os
import random
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings

log = logging.getLogger("precim.browser")


@dataclass(frozen=True)
class Page:
    url: str  # URL pedida
    final_url: str
    title: str
    html: str


def launch_options() -> dict:
    opts: dict = {"headless": True}
    if settings.chromium_path:
        opts["executable_path"] = settings.chromium_path
    if hasattr(os, "geteuid") and os.geteuid() == 0:  # contêiner roda como root
        opts["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    return opts


async def render_pages(
    urls: list[str], *, pause: tuple[float, float], blocked: Callable[[Page], bool],
    scroll: bool = False, settle_ms: int = 3000,
) -> tuple[list[Page], bool]:
    """Abre cada URL em sequência (com pausa). Retorna (páginas lidas, foi_bloqueado).

    Se `blocked(page)` for verdadeiro, para na hora e devolve bloqueado=True.
    """
    from playwright.async_api import async_playwright  # import tardio: só quem usa paga

    pages: list[Page] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_options())
        try:
            ctx = await browser.new_context(
                locale="pt-BR", timezone_id="America/Sao_Paulo",
                viewport={"width": 1366, "height": 850})
            tab = await ctx.new_page()
            for i, url in enumerate(urls):
                if i:
                    await asyncio.sleep(random.uniform(*pause))
                try:
                    await tab.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    await tab.wait_for_timeout(settle_ms)
                    if scroll:  # rolagem leve para carregar os cards, como uma pessoa faria
                        for _ in range(3):
                            await tab.mouse.wheel(0, 900)
                            await tab.wait_for_timeout(1200)
                    page = Page(url, tab.url, await tab.title(), await tab.content())
                except Exception:  # rede/navegador: só essa página falha
                    log.exception("falha ao abrir %s", url)
                    continue
                if blocked(page):
                    return pages, True
                pages.append(page)
        finally:
            await browser.close()
    return pages, False
