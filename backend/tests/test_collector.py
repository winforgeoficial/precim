import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import collector
from app.db.models import Alert, Base, Listing, PriceSnapshot, Product
from app.stores.base import Offer


class FakeStore:
    name = "fake"

    def __init__(self, price):
        self.price = price

    async def fetch(self, url):
        return Offer(price=self.price, url=url, in_stock=True)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.mark.asyncio
async def test_grava_snapshot_e_notifica_uma_vez(session, monkeypatch):
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(collector, "send_telegram", fake_send)
    monkeypatch.setattr(collector, "store_for_url", lambda url: FakeStore(250))

    product = Product(name="SSD 1TB", capacity_gb=1000)
    product.alerts.append(Alert(target_price=300))
    listing = Listing(product=product, store="fake", url="https://x/1")
    session.add_all([product, listing])
    session.commit()

    await collector.scan_listing(session, listing)
    await collector.scan_listing(session, listing)  # cooldown: não repete

    assert len(sent) == 1
    assert "SSD 1TB" in sent[0]
    assert len(session.scalars(select(PriceSnapshot)).all()) == 2
