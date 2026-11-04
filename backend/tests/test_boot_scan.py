from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.cadence import Cadence
from app.db.models import Base, HuntOffer, SearchWatch


def _setup(monkeypatch, seen_at):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as s:
        if seen_at:
            w = SearchWatch(query="ssd", target_price=1)
            s.add(w)
            s.flush()
            s.add(HuntOffer(watch_id=w.id, name="n", merchant="m", price=1, url="u", seen_at=seen_at))
            s.commit()
    monkeypatch.setattr(main, "SessionLocal", Session)


def test_varre_logo_ao_subir_sem_historico(monkeypatch):
    _setup(monkeypatch, None)
    assert main._first_delay_seconds(Cadence((30,), 0)) == main.BOOT_SCAN_DELAY_SECONDS


def test_nao_varre_de_novo_se_varreu_ha_pouco(monkeypatch):
    _setup(monkeypatch, datetime.now(timezone.utc) - timedelta(minutes=5))
    assert main._first_delay_seconds(Cadence((30,), 0)) == 30 * 60


def test_varre_logo_se_ultima_varredura_antiga(monkeypatch):
    _setup(monkeypatch, datetime.now(timezone.utc) - timedelta(hours=2))
    assert main._first_delay_seconds(Cadence((30,), 0)) == main.BOOT_SCAN_DELAY_SECONDS
