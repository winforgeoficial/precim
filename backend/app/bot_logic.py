"""Comandos do bot: texto entra, texto sai. Sem dependência do Telegram (fácil de testar)."""

import re
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.alerts import price_per_gb
from app.db.models import Listing, PriceSnapshot, SearchWatch
from app.notify.telegram import brl
from app.services import ServiceError

AJUDA = """🐷 <b>Precinho — comandos</b>

/resumo — as melhores ofertas agora
/cacar — caçar agora (espera de 5 min entre usos)
/lista — o que estou caçando e acompanhando

<b>Criar</b>
/caca <i>termos</i> [min=1000] [alvo=700] [rgb=0,6]
   ex.: <code>/caca ssd nvme 1tb min=1000 alvo=700</code>
   min = GB mínimos · alvo = preço-alvo (R$) · rgb = R$/GB máximo
/url <i>link-kabum</i> <i>nome</i> [gb=480] [alvo=450] [rgb=0,6]

<b>Gerenciar</b> (use o código da /lista: c1 = caça, p1 = produto)
/alvo c1 650 — muda o preço-alvo
/pausar c1 · /retomar c1
/remover c1"""

_REF = re.compile(r"^([cp])(\d+)$", re.IGNORECASE)
_KEYS = {"min": "min_capacity_gb", "gb": "capacity_gb", "alvo": "target_price",
         "rgb": "max_price_per_gb"}


def _number(raw: str) -> float:
    try:
        return float(raw.replace(",", "."))
    except ValueError as exc:
        raise ServiceError(f"“{raw}” não é um número") from exc


def parse_options(tokens: list[str]) -> tuple[list[str], dict[str, float]]:
    """Separa os termos livres das opções chave=valor."""
    words: list[str] = []
    opts: dict[str, float] = {}
    for tok in tokens:
        key, sep, value = tok.partition("=")
        if sep and key.lower() in _KEYS:
            opts[_KEYS[key.lower()]] = _number(value)
        else:
            words.append(tok)
    return words, opts


def parse_ref(token: str) -> tuple[str, int]:
    m = _REF.match(token or "")
    if not m:
        raise ServiceError("Use o código da /lista, como c1 (caça) ou p1 (produto)")
    return m.group(1).lower(), int(m.group(2))


def _int(v: float | None) -> int | None:
    return int(v) if v is not None else None


def cmd_lista(session: Session) -> str:
    lines: list[str] = []
    searches = session.scalars(select(SearchWatch)).all()
    if searches:
        lines.append("<b>🔎 Caças</b>")
        for w in searches:
            goals = []
            if w.min_capacity_gb:
                goals.append(f"≥{w.min_capacity_gb} GB")
            if w.target_price is not None:
                goals.append(f"até {brl(float(w.target_price))}")
            if w.max_price_per_gb is not None:
                goals.append(f"{brl(w.max_price_per_gb)}/GB")
            pause = "" if w.active else " ⏸"
            lines.append(f"c{w.id} · “{escape(w.query)}” {' · '.join(goals)}{pause}")
    listings = session.scalars(select(Listing)).all()
    if listings:
        lines.append("\n<b>📈 Produtos</b>")
        for lst in listings:
            last = session.scalar(select(PriceSnapshot).where(PriceSnapshot.listing_id == lst.id)
                                  .order_by(PriceSnapshot.captured_at.desc()).limit(1))
            price = brl(float(last.price)) if last else "sem preço"
            pause = "" if lst.active else " ⏸"
            lines.append(f"p{lst.id} · {escape(lst.product.name)} ({lst.store}) — {price}{pause}")
    return "\n".join(lines) if lines else "Nada por aqui ainda. Tente /caca ssd nvme 1tb alvo=700"


def cmd_caca(session: Session, args: list[str]) -> str:
    words, opts = parse_options(args)
    if "capacity_gb" in opts or not words:
        raise ServiceError("Uso: /caca <termos> [min=1000] [alvo=700] [rgb=0,6]")
    watch = services.add_search(
        session, query=" ".join(words), min_capacity_gb=_int(opts.get("min_capacity_gb")),
        target_price=opts.get("target_price"), max_price_per_gb=opts.get("max_price_per_gb"))
    return f"Caça c{watch.id} criada! 🐷 Vou farejar “{escape(watch.query)}”."


async def cmd_url(session: Session, args: list[str]) -> str:
    if not args or not args[0].lower().startswith("http"):
        raise ServiceError("Uso: /url <link-da-kabum> <nome> [gb=480] [alvo=450]")
    words, opts = parse_options(args[1:])
    if not words:
        raise ServiceError("Falta o nome do produto depois do link")
    listing, price = await services.add_tracked(
        session, url=args[0], name=" ".join(words), capacity_gb=_int(opts.get("capacity_gb")),
        target_price=opts.get("target_price"), max_price_per_gb=opts.get("max_price_per_gb"))
    now = f"preço agora: {brl(price)}" if price else "ainda sem preço (tento na próxima varredura)"
    return f"Acompanhando p{listing.id}! 🐷 {now}"


def cmd_alvo(session: Session, args: list[str]) -> str:
    if len(args) != 2:
        raise ServiceError("Uso: /alvo c1 650")
    kind, ident = parse_ref(args[0])
    value = _number(args[1])
    if kind == "c":
        watch = session.get(SearchWatch, ident)
        if not watch:
            raise ServiceError("Caça não encontrada")
        watch.target_price = value
    else:
        listing = session.get(Listing, ident)
        if not listing:
            raise ServiceError("Produto não encontrado")
        alerts = listing.product.alerts
        if not alerts:
            raise ServiceError("Produto sem alerta configurado")
        alerts[0].target_price = value
        alerts[0].last_notified_at = None
    session.commit()
    return f"Alvo de {args[0].lower()} agora é {brl(value)} 🎯"


def cmd_remover(session: Session, args: list[str]) -> str:
    kind, ident = parse_ref(args[0] if args else "")
    (services.remove_search if kind == "c" else services.remove_tracked)(session, ident)
    return f"{args[0].lower()} removido. 🗑"


def _set_active(session: Session, args: list[str], active: bool) -> str:
    kind, ident = parse_ref(args[0] if args else "")
    obj = session.get(SearchWatch if kind == "c" else Listing, ident)
    if not obj:
        raise ServiceError("Não encontrado")
    obj.active = active
    session.commit()
    return f"{args[0].lower()} {'retomado ▶️' if active else 'pausado ⏸'}"


def cmd_pausar(session: Session, args: list[str]) -> str:
    return _set_active(session, args, False)


def cmd_retomar(session: Session, args: list[str]) -> str:
    return _set_active(session, args, True)


def cmd_resumo(session: Session, limit: int = 5) -> str:
    offers = services.build_hunt(session)[:limit]
    if not offers:
        return "Ainda sem ofertas na toca. Crie uma caça com /caca ou use /cacar."
    lines = ["🐷 <b>Melhores ofertas agora</b>"]
    for o in offers:
        tag = "🔥 " if o["is_deal"] else ""
        ppg = price_per_gb(o["price"], o["capacity_gb"])
        extra = f" · {brl(ppg)}/GB" if ppg else ""
        lines.append(f"{tag}<b>{brl(o['price'])}</b>{extra}\n{escape(o['name'])}\n"
                     f"🏪 {escape(o['merchant'])} — {escape(o['url'])}")
    return "\n\n".join(lines)


async def cmd_cacar(session: Session) -> str:
    sent = await services.run_manual_hunt(session)
    return f"Caçada feita! 🎉 {sent} oferta(s) avisada(s)." if sent else \
        "Caçada feita. Nada novo para avisar. Veja /resumo."
