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
