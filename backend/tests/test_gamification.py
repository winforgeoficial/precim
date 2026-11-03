from app.gamification import Stats, achievements, level, xp


def test_nivel_inicial_e_progresso():
    lv = level(xp(Stats()))
    assert lv["level"] == 1 and lv["progress"] == 0
    assert level(5)["title"] == "Farejador"
    assert level(10_000)["next_at"] is None and level(10_000)["progress"] == 1.0


def test_conquistas():
    a = {x["id"]: x["unlocked"] for x in achievements(Stats(scans=12, alerts_sent=1, tracked=1))}
    assert a["primeira-pista"] and a["farejador"] and a["achou"]
    assert not a["queda-20"] and not a["persistente"]
