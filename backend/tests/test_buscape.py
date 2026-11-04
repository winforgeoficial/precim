from pathlib import Path

import pytest

from app.aggregators.buscape import ParseError, parse_capacity_gb, parse_search_html

FIX = Path(__file__).parent / "fixtures" / "buscape" / "busca_ssd.html"


def test_capacidade():
    assert parse_capacity_gb("SSD Kingston 1TB NVMe") == 1000
    assert parse_capacity_gb("SSD 480GB SATA") == 480
    assert parse_capacity_gb("SSD sem capacidade") is None


def test_parse_hits():
    hits = parse_search_html(FIX.read_text())
    assert hits
    assert all(h.price > 0 and "ssd" in h.name.lower() for h in hits)
    assert any(h.merchant == "Magazine Luiza" for h in hits)
    assert any(h.merchant.startswith("vários") for h in hits)


def test_layout_quebrado():
    with pytest.raises(ParseError):
        parse_search_html("<html></html>")


@pytest.mark.parametrize("titulo,esperado", [
    ("SSD M.2 Kingston NVMe 1.000GB 1TB", 1000),
    ("SSD M.2 Kingston NVMe 2.000GB / 2TB", 2000),
    ("SSD 1TB Sandisk", 1000),
    ("SSD 1 TB WD Blue", 1000),
    ("SSD 1000GB Patriot", 1000),
    ("SSD 960GB Kingston DC600M", 960),
    ("SSD 1,5TB", 1500),
    ("SSD 480GB SATA III 2.5", 480),
    ("SSD 512GB leitura 3500MB/s", 512),
    ("SSD 1TB leitura até 7 GB/s", 1000),
    ("SSD 250GB + cache 4GB", 250),
    ("Ssd Patriot P210s1tb25", None),
    ("SSD sem capacidade", None),
])
def test_capacidade_casos_reais(titulo, esperado):
    assert parse_capacity_gb(titulo) == esperado
