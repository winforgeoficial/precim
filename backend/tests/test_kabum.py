from pathlib import Path

import pytest

from app.stores.kabum import ParseError, parse_product_html

FIX = Path(__file__).parent / "fixtures" / "kabum"
URL = "https://www.kabum.com.br/produto/781777/ssd"


def test_desconto_a_vista():
    offer = parse_product_html((FIX / "ssd_desconto.html").read_text(), URL)
    assert offer.price == 539.1
    assert offer.old_price == 599
    assert offer.in_stock is True


def test_esgotado():
    offer = parse_product_html((FIX / "ssd_esgotado.html").read_text(), URL)
    assert offer.price == 599
    assert offer.old_price is None
    assert offer.in_stock is False


def test_layout_quebrado():
    with pytest.raises(ParseError):
        parse_product_html("<html></html>", URL)
