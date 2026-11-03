import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bot, bot_logic, services
from app.db.models import Base, HuntOffer, SearchWatch
from app.services import CooldownError, ServiceError


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def test_parse_options():
    words, opts = bot_logic.parse_options(["ssd", "nvme", "1tb", "min=1000", "alvo=700,50", "rgb=0,6"])
    assert words == ["ssd", "nvme", "1tb"]
    assert opts == {"min_capacity_gb": 1000, "target_price": 700.5, "max_price_per_gb": 0.6}


def test_parse_options_numero_invalido():
    with pytest.raises(ServiceError):
        bot_logic.parse_options(["alvo=abc"])


def test_parse_ref():
    assert bot_logic.parse_ref("C3") == ("c", 3)
    with pytest.raises(ServiceError):
        bot_logic.parse_ref("3")


def test_caca_lista_alvo_pausa_remove(session):
    assert "c1 criada" in bot_logic.cmd_caca(session, ["ssd", "nvme", "min=1000", "alvo=700"])
    assert "c1 ·" in bot_logic.cmd_lista(session)
    assert "R$ 650,00" in bot_logic.cmd_alvo(session, ["c1", "650"])
    assert float(session.get(SearchWatch, 1).target_price) == 650
    assert "pausado" in bot_logic.cmd_pausar(session, ["c1"])
    assert "⏸" in bot_logic.cmd_lista(session)
    assert "retomado" in bot_logic.cmd_retomar(session, ["c1"])
    bot_logic.cmd_remover(session, ["c1"])
    assert session.get(SearchWatch, 1) is None


def test_caca_sem_meta_ou_termos(session):
    with pytest.raises(ServiceError):
        bot_logic.cmd_caca(session, ["ssd"])  # sem alvo nem rgb
    with pytest.raises(ServiceError):
        bot_logic.cmd_caca(session, ["alvo=100"])  # sem termos


def test_remover_inexistente(session):
    with pytest.raises(ServiceError):
        bot_logic.cmd_remover(session, ["c99"])


def test_html_do_usuario_e_escapado(session):
    bot_logic.cmd_caca(session, ["<b>x</b>", "alvo=10"])
    assert "<b>x</b>" not in bot_logic.cmd_lista(session)


def test_resumo_vazio_e_com_oferta(session):
    assert "Ainda sem ofertas" in bot_logic.cmd_resumo(session)
    w = bot_logic.services.add_search(session, query="ssd", target_price=700)
    session.add(HuntOffer(watch_id=w.id, name="SSD 1TB", merchant="Kabum", price=500,
                          capacity_gb=1000, url="https://x"))
    session.commit()
    out = bot_logic.cmd_resumo(session)
    assert "🔥" in out and "R$ 500,00" in out and "R$ 0,50/GB" in out


@pytest.mark.asyncio
async def test_url_rejeita_loja_desconhecida(session):
    with pytest.raises(ServiceError):
        await bot_logic.cmd_url(session, ["https://loja-desconhecida.com/x", "SSD"])
    with pytest.raises(ServiceError):
        await bot_logic.cmd_url(session, ["nao-e-link"])


@pytest.mark.asyncio
async def test_cacar_respeita_espera(session, monkeypatch):
    async def fake_scan(s, w):
        return 0
    monkeypatch.setattr(services, "scan_search", fake_scan)
    services._last_manual_hunt = None
    assert "Caçada feita" in await bot_logic.cmd_cacar(session)
    with pytest.raises(CooldownError):
        await bot_logic.cmd_cacar(session)


def test_autorizacao_so_do_chat_configurado(monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_chat_id", "123")
    assert bot.authorized(123) and not bot.authorized(456) and not bot.authorized(None)
    monkeypatch.setattr(bot.settings, "telegram_chat_id", "")
    assert not bot.authorized(123)  # sem chat configurado, ninguém comanda


class _FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.sent.append(text)


def _update(chat_id):
    from types import SimpleNamespace
    msg = _FakeMessage()
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=msg), msg


@pytest.mark.asyncio
async def test_handler_bloqueia_estranho_e_atende_dono(monkeypatch, session):
    from contextlib import contextmanager
    from types import SimpleNamespace

    monkeypatch.setattr(bot.settings, "telegram_chat_id", "123")

    @contextmanager
    def fake_session_local():
        yield session

    monkeypatch.setattr(bot, "SessionLocal", fake_session_local)
    handler = bot._guarded(bot._lista)

    update, msg = _update(999)
    await handler(update, SimpleNamespace(args=[]))
    assert "uso pessoal" in msg.sent[0]
    assert session.query(SearchWatch).count() == 0

    caca = bot._guarded(bot._sync(bot_logic.cmd_caca))
    update, msg = _update(999)
    await caca(update, SimpleNamespace(args=["ssd", "alvo=1"]))
    assert session.query(SearchWatch).count() == 0  # estranho não cria nada

    update, msg = _update(123)
    await caca(update, SimpleNamespace(args=["ssd", "alvo=1"]))
    assert "criada" in msg.sent[0] and session.query(SearchWatch).count() == 1

    update, msg = _update(123)
    await caca(update, SimpleNamespace(args=["ssd"]))  # sem meta -> aviso amigável
    assert msg.sent[0].startswith("⚠️")


@pytest.mark.asyncio
async def test_start_revela_chat_id_so_sem_configuracao(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(bot.settings, "telegram_chat_id", "")
    update, msg = _update(777)
    await bot.start(update, SimpleNamespace())
    assert "777" in msg.sent[0]

    monkeypatch.setattr(bot.settings, "telegram_chat_id", "123")
    update, msg = _update(777)
    await bot.start(update, SimpleNamespace())
    assert "777" not in msg.sent[0]


def test_aplicacao_registra_todos_os_comandos(monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_token", "123456:ABC-fake")
    app = bot.build_application()
    names = {c for h in app.handlers[0] for c in getattr(h, "commands", [])}
    assert names >= {n for n, _ in bot.COMMANDS} | {"start"}
