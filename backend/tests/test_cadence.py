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


def test_padrao_e_de_uma_hora_com_jitter_de_ate_5_min():
    from app.cadence import DEFAULT_CYCLE

    assert DEFAULT_CYCLE == (60,)
    c = Cadence()
    for _ in range(30):
        assert 3600 <= c.next_delay_seconds() <= 3600 + 300
