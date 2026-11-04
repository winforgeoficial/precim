from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import search_collector
from app.aggregators.buscape import Hit
from app.db.models import Base, HuntOffer, SearchWatch
from app.stores import kabum_catalog as kc
from app.stores.kabum import parse_product_html

FIX = Path(__file__).parent / "fixtures" / "kabum"


def _items():
    return kc.discover((FIX / "sitemap_amostra.xml").read_text())


def test_discover_so_ssd_de_verdade():
    ids = [i.url.split("/produto/")[1].split("/")[0] for i in _items()]
    assert ids == ["111", "112", "113", "114", "118"]  # sem NAS, gaveta ou memória


def test_capacidade_pelo_slug():
    caps = {i.url.split("/")[4]: i.capacity_gb for i in _items()}
    assert caps == {"111": 1000, "112": 480, "113": 2000, "114": 960, "118": 1000}


def test_filtro_por_capacidade_e_termos():
    q = ["ssd nvme 1tb"]
    ids = lambda items: [i.url.split("/")[4] for i in items]
    got = [i for i in _items() if kc.matches(i, q, 960)]
    assert ids(got) == ["111", "113", "118"]  # nvme e >= 960 GB; o portátil 960 não é nvme
    assert [i for i in _items() if kc.matches(i, ["ssd"], 960)] and len(
        [i for i in _items() if kc.matches(i, ["ssd"], 960)]) == 4
    # várias buscas: basta uma casar
    assert len([i for i in _items() if kc.matches(i, ["ssd sata", "ssd nvme"], None)]) == 4


def test_kabum_parse_traz_nome():
    offer = parse_product_html((FIX / "ssd_desconto.html").read_text(), "https://x")
    assert offer.name and "SSD" in offer.name.upper()


# ---------- coletor ----------

@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def _direct_hit(price=500, stock=True):
    return Hit(name="SSD Kingston NV3 1TB", price=price, merchant="KaBuM!", url="https://k/1",
               capacity_gb=1000, source="kabum", verified=True, in_stock=stock)


@pytest.mark.asyncio
async def test_telegram_so_recebe_ofertas_conferidas(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    watch = SearchWatch(query="ssd nvme", target_price=900, min_capacity_gb=960)
    session.add(watch)
    session.commit()

    await search_collector._store_and_alert(session, watch, "kabum", [_direct_hit()])
    agg = Hit(name="SSD Magalu 960", price=400, merchant="Magazine Luiza", url="u", capacity_gb=960)
    n = await search_collector._store_and_alert(session, watch, "buscape", [agg])

    assert n == 0 and len(sent) == 1  # a do Buscapé (R$ 400, bem abaixo da meta) NÃO foi ao grupo
    assert search_collector.VERIFIED_NOTE in sent[0] and "Em estoque" in sent[0]
    rows = {o.source: o for o in session.scalars(select(HuntOffer)).all()}
    assert rows["kabum"].verified is True
    assert rows["buscape"].verified is False  # mas continua listada no painel


@pytest.mark.asyncio
async def test_sem_estoque_lista_mas_nao_avisa(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    watch = SearchWatch(query="ssd", target_price=900)
    session.add(watch)
    session.commit()
    await search_collector._store_and_alert(session, watch, "kabum", [_direct_hit(stock=False)])
    assert sent == [] and session.query(HuntOffer).count() == 1


@pytest.mark.asyncio
async def test_fontes_nao_apagam_uma_a_outra(session, monkeypatch):
    async def fake_send(text):
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    watch = SearchWatch(query="ssd", target_price=900)
    session.add(watch)
    session.commit()
    await search_collector._store_and_alert(session, watch, "kabum", [_direct_hit()])
    await search_collector._store_and_alert(session, watch, "buscape", [])  # varredura vazia
    assert [o.source for o in session.scalars(select(HuntOffer)).all()] == ["kabum"]


@pytest.mark.asyncio
async def test_coleta_direta_respeita_intervalo(session, monkeypatch):
    chamadas = []

    async def fake_sitemap():
        chamadas.append(1)
        return (FIX / "sitemap_amostra.xml").read_text()

    async def fake_crawl(items):
        return [_direct_hit()]

    async def fake_send(text):
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(kc, "fetch_sitemap", fake_sitemap)
    monkeypatch.setattr(kc, "crawl", fake_crawl)
    watch = SearchWatch(query="ssd nvme", target_price=900, min_capacity_gb=960)
    session.add(watch)
    session.commit()

    await search_collector.scan_direct_kabum(session, watch)  # nunca rodou: roda
    await search_collector.scan_direct_kabum(session, watch)  # há pouco: pula
    assert len(chamadas) == 1
    await search_collector.scan_direct_kabum(session, watch, force=True)  # força
    assert len(chamadas) == 2


def test_migracao_adiciona_colunas_em_banco_antigo(tmp_path, monkeypatch):
    from sqlalchemy import inspect, text

    from app.db import session as dbs

    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as c:  # esquema antigo, sem as colunas novas
        c.execute(text("CREATE TABLE hunt_offers (id INTEGER PRIMARY KEY, watch_id INTEGER, "
                       "name VARCHAR, merchant VARCHAR, price NUMERIC, capacity_gb INTEGER, "
                       "lowering_pct FLOAT, url VARCHAR, seen_at DATETIME)"))
        c.execute(text("INSERT INTO hunt_offers (watch_id,name,merchant,price,url) "
                       "VALUES (1,'n','m',10,'u')"))
    monkeypatch.setattr(dbs, "engine", engine)
    dbs._ensure_columns()
    cols = {c["name"] for c in inspect(engine).get_columns("hunt_offers")}
    assert {"source", "verified", "in_stock"} <= cols
    with engine.connect() as c:
        row = c.execute(text("SELECT source, verified FROM hunt_offers")).one()
    assert row == ("buscape", 0)  # linhas antigas viram "buscapé, não verificada"


@pytest.mark.asyncio
async def test_coleta_direta_nao_pula_para_4h_por_causa_do_jitter(session):
    from datetime import datetime, timedelta, timezone

    watch = SearchWatch(query="ssd", target_price=900)
    session.add(watch)
    session.flush()
    agora = datetime.now(timezone.utc)
    session.add(HuntOffer(watch_id=watch.id, name="n", merchant="m", price=1, url="u",
                          source="kabum", seen_at=agora - timedelta(hours=2, minutes=50)))
    session.commit()
    assert search_collector._direct_is_due(session, watch, "kabum") is True  # 2h50 ≈ 3h
    session.query(HuntOffer).delete()
    session.add(HuntOffer(watch_id=watch.id, name="n", merchant="m", price=1, url="u",
                          source="kabum", seen_at=agora - timedelta(hours=2)))
    session.commit()
    assert search_collector._direct_is_due(session, watch, "kabum") is False  # 2h: ainda cedo
