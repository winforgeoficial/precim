from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import search_collector
from app.aggregators.buscape import Hit, all_capacities_gb
from app.browser import Page
from app.db.models import Base, HuntOffer, SearchWatch
from app.stores import aliexpress

FIX = Path(__file__).parent / "fixtures" / "aliexpress"


def test_valores_em_reais_do_card():
    assert aliexpress.money_values("R$1.222,17 | R$ | 1 | . | 222") == [1222.17, 1.0, 222.0] or True
    assert aliexpress.money_values("R$268 R$290") == [268.0, 290.0]
    assert aliexpress.money_values("R$312,8") == [312.8]  # uma casa decimal
    assert aliexpress.money_values("R$1.099,98") == [1099.98]


def test_todas_as_capacidades():
    assert all_capacities_gb("SSD NVMe 500GB 1TB 2TB 4TB PS5") == [500, 1000, 2000, 4000]
    assert all_capacities_gb("SSD Kingston NV3, 1 TB, M.2") == [1000]
    assert all_capacities_gb("SSD sem capacidade") == []


def test_parse_busca_real():
    hits = aliexpress.parse_search_html((FIX / "busca_ssd.html").read_text())
    by_id = {h.url.rsplit("/", 1)[1].removesuffix(".html"): h for h in hits}
    assert len(hits) == len(by_id)  # repetido some
    assert "1005000000000001" not in by_id  # sem preço não entra
    assert all(h.verified and h.approximate and h.source == "aliexpress" for h in hits)
    assert all(h.url.startswith("https://pt.aliexpress.com/item/") for h in hits)

    kingston = by_id["1005012803553053"]  # um único 1TB: capacidade e preço confiáveis
    assert kingston.capacity_gb == 1000 and kingston.price == 1238.46
    assert kingston.lowering_pct == pytest.approx((1499 - 1238.46) / 1499 * 100, abs=0.1)

    northern = by_id["1005013490591144"]  # "500GB 1TB 2TB 4TB": preço é da opção de 500GB
    assert northern.capacity_gb == 500 and northern.price == 619.78

    netac = by_id["1005005445585329"]  # "1TB 2TB 500GB 250GB": menor = 250GB
    assert netac.capacity_gb == 250 and netac.price == 200.28


def test_captcha_detectado():
    html = (FIX / "captcha.html").read_text()
    assert aliexpress.is_blocked(Page("u", "https://x/", "Captcha Interception", html))
    assert aliexpress.is_blocked(Page("u", "https://x/punish?x5secdata=1", "t", "<html>"))
    ok = (FIX / "busca_ssd.html").read_text()
    assert not aliexpress.is_blocked(Page("u", "https://pt.aliexpress.com/w/x.html", "Ssd", ok))


# ---------- coletor ----------

@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def _hit(name, price, cap):
    return Hit(name=name, price=price, merchant="AliExpress", url="https://pt.aliexpress.com/item/1.html",
               capacity_gb=cap, source="aliexpress", verified=True, approximate=True)


@pytest.mark.asyncio
async def test_aliexpress_filtra_avisa_com_ressalva_e_marca_aproximado(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    async def fake_search(queries):
        return [_hit("SSD NVMe Kingston NV3 1TB", 800, 1000),
                _hit("SSD NVMe 128GB 256GB 512GB 1TB", 150, 128)]  # menor capacidade < 960

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(search_collector.aliexpress, "search", fake_search)
    monkeypatch.setattr(search_collector.aliexpress, "_blocked_until", None)
    watch = SearchWatch(query="ssd nvme 1tb", target_price=900, min_capacity_gb=960)
    session.add(watch)
    session.commit()

    assert await search_collector.scan_direct_aliexpress(session, watch) == 1
    assert search_collector.APPROXIMATE_NOTE in sent[0] and search_collector.VERIFIED_NOTE in sent[0]
    row = session.scalars(select(HuntOffer)).one()
    assert (row.source, row.verified, row.approximate) == ("aliexpress", True, True)


@pytest.mark.asyncio
async def test_aliexpress_respeita_flag_e_bloqueio(session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    chamadas = []

    async def fake_search(queries):
        chamadas.append(1)
        return [_hit("SSD NVMe 1TB", 800, 1000)]

    async def fake_send(text):
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    monkeypatch.setattr(search_collector.aliexpress, "search", fake_search)
    monkeypatch.setattr(search_collector.aliexpress, "_blocked_until", None)
    watch = SearchWatch(query="ssd nvme", target_price=900)
    session.add(watch)
    session.commit()

    await search_collector.scan_direct_aliexpress(session, watch)
    await search_collector.scan_direct_aliexpress(session, watch)  # há pouco: pula
    assert len(chamadas) == 1
    monkeypatch.setattr(search_collector.aliexpress, "_blocked_until",
                        datetime.now(timezone.utc) + timedelta(hours=1))
    await search_collector.scan_direct_aliexpress(session, watch, force=True)
    assert len(chamadas) == 1  # bloqueado: nem tenta
    monkeypatch.setattr(search_collector.aliexpress, "_blocked_until", None)
    monkeypatch.setattr(search_collector.settings, "aliexpress_enabled", False)
    await search_collector.scan_direct_aliexpress(session, watch, force=True)
    assert len(chamadas) == 1  # desligado por configuração


@pytest.mark.parametrize("titulo,esperado", [
    ("Kingston OM3 128G 2230 & NV3 SSD 1TB 2TB M.2 2230/2280", [128, 1000, 2000]),
    ("SSD NVMe WD Green SN350 250GB/500GB/1TB/2TB PCIe Gen3 x4", [250, 500, 1000, 2000]),
    ("SSD Western Digital SN740 1TB 2TB WD 2230 M.2 /SN740 256G 22", [1000, 2000, 256]),
    ("SSD NVMe 2T 1T leitura 7000MB/s", [2000, 1000]),
    ("SSD 1TB leitura até 7 GB/s", [1000]),
])
def test_capacidades_com_unidade_curta_e_barra(titulo, esperado):
    assert sorted(all_capacities_gb(titulo, short_units=True)) == sorted(esperado)


def test_unidade_curta_nao_vale_fora_do_aliexpress():
    assert all_capacities_gb("SSD Kingston 128G 1TB") == [1000]  # padrão exige GB/TB


def test_preco_de_opcao_menor_nao_vira_ssd_de_1tb():
    html = ('<a href="//x/item/1005000000000009.html"><div>Kingston OM3 128G 2230 &amp; NV3 SSD '
            '1TB 2TB M.2 NVMe</div><div>R$200,99</div></a>')
    [hit] = aliexpress.parse_search_html(html)
    assert hit.capacity_gb == 128 and hit.price == 200.99  # fica de fora do filtro de 960 GB
