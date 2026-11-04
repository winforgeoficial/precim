import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import backup, history, search_collector
from app.aggregators.buscape import Hit
from app.db.models import Base, HuntOffer, OfferPrice, SearchWatch
from app.pricing import is_suspect, reference_ppg
from app.stores import kabum_catalog


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        s.add(SearchWatch(id=1, query="ssd 1tb", min_capacity_gb=960, target_price=2000))
        s.commit()
        yield s


def _hit(price, name="SSD X 1TB", **kw):
    return Hit(name=name, price=price, merchant="Loja", url="https://x", capacity_gb=1000,
               verified=True, **kw)


def test_historico_so_grava_mudanca(session):
    history.record(session, 1, [_hit(500)])
    history.record(session, 1, [_hit(500)])  # igual, dentro de 12 h: não duplica
    history.record(session, 1, [_hit(450)])
    assert len(session.scalars(select(OfferPrice)).all()) == 2
    st = history.stats(session, 1)[_hit(1).key]
    assert (st.low, st.high, st.points) == (450, 500, 2)
    assert history.is_lowest(450, st) and not history.is_lowest(500, st)


def test_historico_ponto_de_vida_apos_12h(session):
    old = datetime.now(timezone.utc) - timedelta(hours=13)
    session.add(OfferPrice(watch_id=1, key=_hit(1).key, price=500, captured_at=old))
    session.commit()
    history.record(session, 1, [_hit(500)])
    assert len(session.scalars(select(OfferPrice)).all()) == 2


def test_historico_apaga_alem_de_90_dias(session):
    session.add(OfferPrice(watch_id=1, key="k", price=1,
                           captured_at=datetime.now(timezone.utc) - timedelta(days=91)))
    session.commit()
    history.record(session, 1, [])
    assert session.scalars(select(OfferPrice)).all() == []


def test_desconto_duvidoso():
    st = history.Stats(low=900, high=1000, points=5, days=10)
    assert history.fake_discount(900, 30, st)  # diz "era ~1286", nunca passou de 1000
    assert not history.fake_discount(900, 10, st)  # "era 1000": confere
    assert not history.fake_discount(900, 30, history.Stats(900, 1000, 2, days=0.5))  # pouco histórico
    assert not history.fake_discount(900, 30, None)


def test_preco_suspeito():
    assert reference_ppg([1.5, 1.4]) is None  # poucas ofertas
    ref = reference_ppg([1.2, 1.5, 1.8])
    assert ref == 1.5
    assert is_suspect(0.38, ref) and not is_suspect(1.0, ref) and not is_suspect(None, ref)


@pytest.mark.asyncio
async def test_aliexpress_suspeito_nao_vai_ao_grupo(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    for i, price in enumerate([1200, 1500, 1800]):  # referência conferida: ~1,5 R$/GB
        session.add(HuntOffer(watch_id=1, name=f"Ref {i}", merchant="Kabum", price=price,
                              capacity_gb=1000, url="u", source="kabum", verified=True))
    session.commit()
    watch = session.get(SearchWatch, 1)
    barato = _hit(383.99, name="ORICIO 1TB", approximate=True, source="aliexpress")
    normal = _hit(1300, name="Marca boa 1TB", approximate=True, source="aliexpress")
    await search_collector._store_and_alert(session, watch, "aliexpress", [barato, normal])
    assert len(sent) == 1 and "Marca boa" in sent[0]


@pytest.mark.asyncio
async def test_alerta_menciona_menor_preco(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(search_collector, "send_telegram", fake_send)
    watch = session.get(SearchWatch, 1)
    await search_collector._store_and_alert(session, watch, "kabum", [_hit(1000)])
    await search_collector._store_and_alert(session, watch, "kabum", [_hit(800)])
    assert "Menor preço" not in sent[0] and "Menor preço" in sent[1]


def test_backup_cria_e_poda(tmp_path, monkeypatch):
    db = tmp_path / "precim.db"
    con = sqlite3.connect(db)
    con.execute("create table t (x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()
    monkeypatch.setattr(backup.settings, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(backup.settings, "backup_dir", "")
    for day in range(1, 4):
        (tmp_path / "backups").mkdir(exist_ok=True)
        (tmp_path / "backups" / f"precim-2020010{day}-000000.db").write_bytes(b"x")
    made = backup.run_backup(keep=2)
    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(names) == 2 and made.name in names
    assert sqlite3.connect(made).execute("select x from t").fetchone() == (42,)
    assert backup.is_recent(tmp_path / "backups")


def test_backup_sem_banco_nao_quebra(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.settings, "database_url", f"sqlite:///{tmp_path}/nao-existe.db")
    assert backup.run_backup() is None
    backup.backup_if_needed()


def test_kabum_ignora_console_e_macbook():
    xml = "".join(f"<loc>https://www.kabum.com.br/produto/{i}/{slug}</loc>" for i, slug in enumerate([
        "ssd-kingston-nv2-1tb-m-2-nvme",
        "ssd-externo-portatil-sandisk-1tb-playstation-5-ps5",
        "console-playstation-5-sony-ssd-1tb-leitor-de-discos",
        "macbook-air-15-chip-m5-1-tb-ssd-meia-noite",
    ]))
    slugs = [i.url for i in kabum_catalog.discover(xml)]
    assert len(slugs) == 2 and all("console" not in u and "macbook" not in u for u in slugs)
