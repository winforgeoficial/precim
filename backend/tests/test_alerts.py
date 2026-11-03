from app.alerts import price_per_gb, should_alert


def test_price_per_gb():
    assert price_per_gb(300, 1000) == 0.3
    assert price_per_gb(300, None) is None


def test_target_price():
    assert should_alert(299, target_price=300)
    assert not should_alert(301, target_price=300)


def test_drop_pct():
    assert should_alert(80, previous_price=100, min_drop_pct=15)
    assert not should_alert(95, previous_price=100, min_drop_pct=15)


def test_price_per_gb_rule():
    assert should_alert(250, capacity_gb=1000, max_price_per_gb=0.3)
    assert not should_alert(400, capacity_gb=1000, max_price_per_gb=0.3)


def test_no_rules_never_alerts():
    assert not should_alert(1)
