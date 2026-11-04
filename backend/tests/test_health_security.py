import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api, health, search_collector
from app.aggregators.buscape import Hit
from app.db.models import Base, SourceStatus
from app.main import same_origin_writes
from app.notify.telegram import format_alert


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


# ---------- Telegram: texto das lojas é escapado ----------

def test_mensagem_escapa_texto_das_lojas():
    h = Hit(name='Kingston 128G & NV3 SSD <1TB> "Pro"', price=800, merchant="Loja <X> & Cia",
            url="https://x/?a=1&b=2", capacity_gb=1000, verified=True)
    msg = search_collector.format_hit(h)
    assert "<1TB>" not in msg and "&lt;1TB&gt;" in msg and "&amp; NV3" in msg
    assert "Loja &lt;X&gt; &amp; Cia" in msg and "a=1&amp;b=2" in msg
    assert msg.count("<b>") == 1 and msg.count("</b>") == 1  # só a tag que nós mesmos pusemos
    assert "&lt;" in format_alert("SSD <x>", "L&L", 1, None, None, None, "u?a&b")


@pytest.mark.asyncio
async def test_erro_do_telegram_traz_o_motivo_sem_vazar_token(monkeypatch):
    import httpx

    from app.notify import telegram as tg

    monkeypatch.setattr(tg.settings, "telegram_token", "123:SEGREDO")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "-1")

    def handler(request):
        return httpx.Response(400, text='{"description":"can\'t parse entities"}')

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(tg.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    with pytest.raises(RuntimeError) as exc:
        await tg.send_telegram("oi")
    assert "400" in str(exc.value) and "parse entities" in str(exc.value)
    assert "SEGREDO" not in str(exc.value)


# ---------- escrita só da mesma origem ----------

def _app():
    app = FastAPI()
    app.middleware("http")(same_origin_writes)

    @app.post("/x")
    def post():
        return {"ok": True}

    @app.get("/x")
    def get():
        return {"ok": True}

    return TestClient(app)


def test_origem_externa_nao_escreve_mas_painel_sim():
    c = _app()
    assert c.post("/x", headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/x", headers={"Origin": "http://testserver"}).status_code == 200  # mesmo host
    assert c.post("/x").status_code == 200  # sem Origin (curl, bot): permitido
    assert c.get("/x", headers={"Origin": "http://evil.example"}).status_code == 200  # leitura livre


# ---------- saúde das fontes ----------

@pytest.mark.asyncio
async def test_aviso_na_terceira_falha_e_na_volta(session, monkeypatch):
    msgs = []

    async def fake_send(text):
        msgs.append(text)
        return True

    monkeypatch.setattr(health, "send_telegram", fake_send)
    for _ in range(2):
        await health.record(session, "kabum", False, "sitemap: ConnectError")
    assert msgs == []  # ainda não
    await health.record(session, "kabum", False, "sitemap: ConnectError")
    await health.record(session, "kabum", False, "sitemap: ConnectError")  # 4ª: não repete o aviso
    assert len(msgs) == 1 and "Kabum" in msgs[0] and "3" in msgs[0]
    await health.record(session, "kabum", True)
    assert len(msgs) == 2 and "voltou" in msgs[1]
    st = session.get(SourceStatus, "kabum")
    assert st.consecutive_failures == 0 and st.warned is False and st.last_ok_at


@pytest.mark.asyncio
async def test_endpoint_de_fontes(session, monkeypatch):
    async def fake_send(text):
        return True

    monkeypatch.setattr(health, "send_telegram", fake_send)
    await health.record(session, "buscape", True)
    await health.record(session, "amazon", False, "sem resultados")

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = lambda: session
    got = {s["source"]: s for s in TestClient(app).get("/api/sources").json()}
    assert got["buscape"]["state"] == "ok" and got["buscape"]["last_ok_at"]
    assert got["amazon"]["state"] == "falhando" and got["amazon"]["failures"] == 1
    assert got["kabum"]["state"] == "aguardando"
