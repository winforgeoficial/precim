from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import search_collector
from app.aggregators.buscape import Hit
from app.db.models import Base, HuntOffer, SearchWatch
from app.matching import matches_terms
from app.stores import amazon

FIX = Path(__file__).parent / "fixtures" / "amazon"


def test_parse_preco_brasileiro():
    assert amazon.parse_price("R$\xa01.329,90") == 1329.90
    assert amazon.parse_price("R$ 949,89") == 949.89
    assert amazon.parse_price("R$\xa02.029,24") == 2029.24
    assert amazon.parse_price("sem preço") is None and amazon.parse_price(None) is None


def test_parse_busca_real():
    hits = amazon.parse_search_html((FIX / "busca_ssd.html").read_text())
    by_asin = {h.url.rsplit("/", 1)[1]: h for h in hits}
    assert len(hits) == len(by_asin)  # ASIN repetido (patrocinado + orgânico) vira um só
    sandisk = by_asin["B0CN3N3591"]
    assert sandisk.price == 899.89 and sandisk.capacity_gb == 1000
    assert sandisk.verified and sandisk.source == "amazon" and sandisk.merchant == "Amazon"
    assert sandisk.url == "https://www.amazon.com.br/dp/B0CN3N3591"
    assert by_asin["B093DP3X4H"].price == 1329.90  # separador de milhar
    assert by_asin["B0822Y6N1C"].capacity_gb == 128
    assert "B0F8B1FLHZ" not in by_asin and "B0HGRK781T" not in by_asin  # gabinetes/adaptadores
    assert "B0SEMPRECO" not in by_asin  # sem preço não entra


def test_captcha_e_detectado():
    assert amazon.is_blocked((FIX / "captcha.html").read_text())
    with pytest.raises(amazon.Blocked):
        amazon.parse_search_html((FIX / "captcha.html").read_text())
    assert not amazon.is_blocked((FIX / "busca_ssd.html").read_text())


def test_matching_de_termos():
    q = ["ssd nvme 1tb"]
    assert matches_terms("SSD Sandisk Plus - 1TB, NVMe, M.2 2280", q)
    assert matches_terms("SSD Kingston NV3 1TB M.2 2280", q)  # m.2 vale como nvme
    assert not matches_terms("SSD WD Verde SATA 1TB, 2,5 polegadas", q)
    assert matches_terms("SSD WD Verde SATA 1TB", ["ssd nvme 1tb", "ssd sata 1tb"])
    assert matches_terms("qualquer coisa", ["ssd 1tb"])  # só ssd+capacidade: sem filtro extra


# ---------- coletor ----------

@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def _hit(name="SSD Sandisk Plus - 1TB, NVMe, M.2", price=899.89, cap=1000):
    return Hit(name=name, price=price, merchant="Amazon", url="https://www.amazon.com.br/dp/B0",
               capacity_gb=cap, source="amazon", verified=True)


@pytest.mark.asyncio
async def test_amazon_filtra_por_capacidade_e_termos_e_avisa(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    async def fake_search(queries):
        return [_hit(), _hit("SSD Kingston 480GB NVMe", 300, 480),
                _hit("SSD WD Verde SATA 1TB", 899.99, 1000)]

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(search_collector.amazon, "search", fake_search)
    monkeypatch.setattr(search_collector.amazon, "_blocked_until", None)
    watch = SearchWatch(query="ssd nvme 1tb", target_price=900, min_capacity_gb=960)
    session.add(watch)
    session.commit()

    assert await search_collector.scan_direct_amazon(session, watch) == 1
    assert search_collector.VERIFIED_NOTE in sent[0] and "899,89" in sent[0]
    rows = session.scalars(select(HuntOffer)).all()
    assert [(r.source, r.verified) for r in rows] == [("amazon", True)]  # só o que casa


@pytest.mark.asyncio
async def test_amazon_respeita_intervalo_bloqueio_e_flag(session, monkeypatch):
    chamadas = []

    async def fake_search(queries):
        chamadas.append(queries)
        return [_hit()]

    async def fake_send(text):
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(search_collector.amazon, "search", fake_search)
    monkeypatch.setattr(search_collector.amazon, "_blocked_until", None)
    watch = SearchWatch(query="ssd nvme 1tb | ssd nvme 960gb", target_price=900)
    session.add(watch)
    session.commit()

    await search_collector.scan_direct_amazon(session, watch)
    assert chamadas == [["ssd nvme 1tb", "ssd nvme 960gb"]]  # uma página por busca
    await search_collector.scan_direct_amazon(session, watch)  # há pouco: pula
    assert len(chamadas) == 1
    await search_collector.scan_direct_amazon(session, watch, force=True)
    assert len(chamadas) == 2

    monkeypatch.setattr(search_collector.amazon, "_blocked_until",
                        datetime.now(timezone.utc) + timedelta(hours=1))
    await search_collector.scan_direct_amazon(session, watch, force=True)
    assert len(chamadas) == 2  # em bloqueio: nem tenta, nem com force

    monkeypatch.setattr(search_collector.amazon, "_blocked_until", None)
    monkeypatch.setattr(search_collector.settings, "amazon_enabled", False)
    await search_collector.scan_direct_amazon(session, watch, force=True)
    assert len(chamadas) == 2  # desligada por configuração
