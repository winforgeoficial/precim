import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import api, services
from app.db.models import Base, HuntOffer, Listing, PriceSnapshot, Product


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = override
    services._last_manual_hunt = None
    c = TestClient(app)
    c.session_factory = Session
    return c


def test_busca_exige_regra(client):
    r = client.post("/api/search-watch", json={"query": "ssd"})
    assert r.status_code == 422


def test_caca_ordena_e_marca_oferta(client):
    sw = client.post("/api/search-watch", json={
        "query": "ssd 1tb", "target_price": 700, "min_capacity_gb": 1000}).json()
    with client.session_factory() as s:
        s.add_all([
            HuntOffer(watch_id=sw["id"], name="SSD A 1TB", merchant="Kabum", price=900,
                      capacity_gb=1000, url="u1"),
            HuntOffer(watch_id=sw["id"], name="SSD B 1TB", merchant="Magalu", price=600,
                      capacity_gb=1000, url="u2"),
        ])
        s.commit()
    offers = client.get("/api/hunt").json()["offers"]
    assert [o["merchant"] for o in offers] == ["Magalu", "Kabum"]
    assert offers[0]["is_deal"] and not offers[1]["is_deal"]
    assert offers[0]["quality"] == 100 and offers[1]["quality"] == 0


def test_mascote_party_quando_ha_oferta(client):
    assert client.get("/api/mascot").json()["mood"] == "sleep"
    sw = client.post("/api/search-watch", json={"query": "ssd", "target_price": 700}).json()
    with client.session_factory() as s:
        s.add(HuntOffer(watch_id=sw["id"], name="SSD", merchant="K", price=100,
                        capacity_gb=500, url="u"))
        s.commit()
    m = client.get("/api/mascot").json()
    assert m["mood"] == "party" and m["level"] >= 1


def test_historico_e_remocao(client):
    with client.session_factory() as s:
        p = Product(name="SSD", capacity_gb=480)
        lst = Listing(product=p, store="kabum", url="https://x/1")
        s.add_all([p, lst])
        s.flush()
        s.add_all([PriceSnapshot(listing_id=lst.id, price=500),
                   PriceSnapshot(listing_id=lst.id, price=450, old_price=500)])
        s.commit()
        lid = lst.id
    h = client.get(f"/api/watch/{lid}/history").json()
    assert [x["price"] for x in h] == [500, 450]
    w = client.get("/api/watch").json()[0]
    assert w["price"] == 450 and w["previous_price"] == 500
    assert client.delete(f"/api/watch/{lid}").status_code == 204
    assert client.get("/api/watch").json() == []
    assert client.delete(f"/api/watch/{lid}").status_code == 404


def test_patch_search_watch(client):
    wid = client.post("/api/search-watch", json={
        "query": "ssd nvme 1tb", "target_price": 900, "min_capacity_gb": 1000}).json()["id"]
    r = client.patch(f"/api/search-watch/{wid}", json={"min_capacity_gb": 960, "active": False})
    assert r.status_code == 200
    body = r.json()
    assert body["min_capacity_gb"] == 960 and body["active"] is False
    assert body["target_price"] == 900 and body["query"] == "ssd nvme 1tb"  # não tocou no resto
    assert body["history_reset"] is False
    r = client.patch(f"/api/search-watch/{wid}", json={"query": "ssd nvme 1tb | ssd nvme 1000gb"})
    assert r.json()["history_reset"] is True
    # null limpa a capacidade; remover a última meta é recusado
    assert client.patch(f"/api/search-watch/{wid}", json={"min_capacity_gb": None}).json()[
        "min_capacity_gb"] is None
    assert client.patch(f"/api/search-watch/{wid}", json={"target_price": None}).status_code == 422
    assert client.patch("/api/search-watch/999", json={"active": True}).status_code == 404
