from app.cadence import Cadence, parse_cycle


def test_ciclo_30_50_60_e_repete():
    c = Cadence((30, 50, 60), jitter_seconds=0)
    assert [c.next_delay_seconds() / 60 for _ in range(5)] == [30, 50, 60, 30, 50]


def test_jitter_dentro_do_limite():
    c = Cadence((30,), jitter_seconds=90)
    for _ in range(50):
        assert 1800 <= c.next_delay_seconds() <= 1890


def test_parse_cycle():
    assert parse_cycle("30, 50,60") == (30, 50, 60)
