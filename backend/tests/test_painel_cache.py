from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import Painel


def test_index_revalida_e_assets_ficam_em_cache(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>oi</html>")
    (tmp_path / "assets" / "app-abc123.js").write_text("x")
    app = FastAPI()
    app.mount("/", Painel(directory=tmp_path, html=True), name="painel")
    c = TestClient(app)
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in c.get("/assets/app-abc123.js").headers
