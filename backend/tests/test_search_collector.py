import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import search_collector
from app.aggregators.buscape import Hit
from app.db.models import Base, HuntOffer, SearchWatch, SeenOffer


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def _hit(price):
    return Hit(name="SSD X 1TB", price=price, merchant="Kabum", url="https://x", capacity_gb=1000,
               verified=True)  # só ofertas conferidas vão ao Telegram


@pytest.mark.asyncio
async def test_avisa_uma_vez_e_so_de_novo_com_queda_real(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    prices = iter([500, 499, 450])

    async def fake_search(query):
        return [_hit(next(prices))]

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(search_collector.buscape, "search", fake_search)
    watch = SearchWatch(query="ssd 1tb", target_price=600, min_capacity_gb=500)
    session.add(watch)
    session.commit()

    for _ in range(3):
        await search_collector.scan_search(session, watch)

    assert len(sent) == 2  # 500 avisa; 499 (queda <3%) não; 450 avisa
    assert float(session.scalars(select(SeenOffer)).one().last_notified_price) == 450


@pytest.mark.asyncio
async def test_ignora_capacidade_menor(session, monkeypatch):
    async def fake_search(query):
        return [Hit(name="SSD 240GB", price=100, merchant="L", url="u", capacity_gb=240)]

    monkeypatch.setattr(search_collector.buscape, "search", fake_search)
    watch = SearchWatch(query="ssd", target_price=600, min_capacity_gb=500)
    session.add(watch)
    session.commit()
    assert await search_collector.scan_search(session, watch) == 0


@pytest.mark.asyncio
async def test_varias_buscas_juntam_e_removem_repetidos(session, monkeypatch):
    monkeypatch.setattr(search_collector, "QUERY_PAUSE_SECONDS", (0, 0))
    chamadas = []

    async def fake_search(query):
        chamadas.append(query)
        if query == "b":
            raise RuntimeError("fora do ar")
        return [_hit(500), _hit(450)] if query == "a" else [_hit(500), _hit(300)]

    monkeypatch.setattr(search_collector.buscape, "search", fake_search)
    hits = await search_collector._collect("a | b | c")
    assert chamadas == ["a", "b", "c"]
    assert sorted(h.price for h in hits) == [300, 450, 500]  # 500 repetido some; "b" falhou, segue


@pytest.mark.asyncio
async def test_todas_as_buscas_falham_retorna_none(monkeypatch):
    monkeypatch.setattr(search_collector, "QUERY_PAUSE_SECONDS", (0, 0))

    async def fake_search(query):
        raise RuntimeError("x")

    monkeypatch.setattr(search_collector.buscape, "search", fake_search)
    assert await search_collector._collect("a | b") is None


@pytest.mark.asyncio
async def test_limite_de_alertas_por_varredura_e_ordem_por_rgb(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    watch = SearchWatch(query="ssd", target_price=900)
    session.add(watch)
    session.commit()
    hits = [Hit(name=f"SSD {i}", price=100 + i * 10, merchant="K", url=f"u{i}", capacity_gb=1000,
                verified=True) for i in range(8)]
    hits.reverse()  # chegam do mais caro ao mais barato

    n = await search_collector._store_and_alert(session, watch, "kabum", hits)
    assert n == search_collector.MAX_ALERTS_PER_SCAN == 5 and len(sent) == 5
    assert "SSD 0" in sent[0] and "SSD 4" in sent[-1]  # os 5 mais baratos, do melhor ao pior
    assert session.query(HuntOffer).count() == 8  # todas continuam no painel

    n2 = await search_collector._store_and_alert(session, watch, "kabum", hits)
    assert n2 == 3  # as 3 restantes saem na varredura seguinte; as 5 já avisadas não repetem
