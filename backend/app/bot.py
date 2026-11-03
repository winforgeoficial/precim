"""Ligação com o Telegram (long polling). Só atende o chat configurado."""

import logging
from collections.abc import Awaitable, Callable
from html import escape

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from app import bot_logic
from app.core.config import settings
from app.db.session import SessionLocal
from app.services import ServiceError

log = logging.getLogger("precim.bot")

COMMANDS = [
    ("resumo", "Melhores ofertas agora"), ("cacar", "Caçar agora"), ("lista", "O que estou caçando"),
    ("caca", "Criar uma caça por busca"), ("url", "Acompanhar link da Kabum"),
    ("alvo", "Mudar preço-alvo"), ("pausar", "Pausar"), ("retomar", "Retomar"),
    ("remover", "Remover"), ("ajuda", "Ver comandos"),
]


def authorized(chat_id: int | None) -> bool:
    return bool(settings.telegram_chat_id) and str(chat_id) == str(settings.telegram_chat_id)


async def _reply(update: Update, text: str) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat and not settings.telegram_chat_id:
        # Setup: revela só o id do chat para a pessoa colocar no .env. Nenhum comando funciona ainda.
        await _reply(update, f"Oi! 🐷 Seu chat id é <code>{chat.id}</code>.\n"
                     "Coloque em <code>PRECIM_TELEGRAM_CHAT_ID</code> no .env e reinicie.")
    elif chat and authorized(chat.id):
        await _reply(update, bot_logic.AJUDA)
    else:
        await _reply(update, "Este bot é de uso pessoal. 🔒")


def _guarded(fn: Callable[..., Awaitable[str]]):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat or not authorized(chat.id):
            await _reply(update, "Este bot é de uso pessoal. 🔒")
            return
        try:
            with SessionLocal() as session:
                text = await fn(session, context.args or [])
        except ServiceError as exc:
            text = f"⚠️ {escape(str(exc))}"
        except Exception:
            log.exception("erro em comando do bot")
            text = "Ops, deu algo errado aqui. Tente de novo em instantes."
        await _reply(update, text)
    return handler


def _sync(fn):
    async def wrapped(session, args):
        return fn(session, args)
    return wrapped


async def _ajuda(session, args) -> str:
    return bot_logic.AJUDA


async def _lista(session, args) -> str:
    return bot_logic.cmd_lista(session)


async def _resumo(session, args) -> str:
    return bot_logic.cmd_resumo(session)


async def _cacar(session, args) -> str:
    return await bot_logic.cmd_cacar(session)


async def _url(session, args) -> str:
    return await bot_logic.cmd_url(session, args)


def build_application() -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    table: dict[str, Callable[..., Awaitable[str]]] = {
        "ajuda": _ajuda, "lista": _lista, "resumo": _resumo, "cacar": _cacar, "url": _url,
        "caca": _sync(bot_logic.cmd_caca), "alvo": _sync(bot_logic.cmd_alvo),
        "remover": _sync(bot_logic.cmd_remover), "pausar": _sync(bot_logic.cmd_pausar),
        "retomar": _sync(bot_logic.cmd_retomar),
    }
    for name, fn in table.items():
        app.add_handler(CommandHandler(name, _guarded(fn)))
    return app


async def start_bot() -> Application | None:
    """Sobe o polling se houver token. Falha de rede não derruba a API."""
    if not settings.telegram_token:
        log.info("Telegram sem token: bot desligado")
        return None
    try:
        app = build_application()
        await app.initialize()
        await app.bot.set_my_commands([BotCommand(n, d) for n, d in COMMANDS])
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("bot do Telegram ligado")
        return app
    except Exception:
        log.exception("não consegui ligar o bot do Telegram")
        return None


async def stop_bot(app: Application | None) -> None:
    if not app:
        return
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
