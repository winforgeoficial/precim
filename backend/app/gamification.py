"""Nível do mascote e conquistas — calculados a partir dos dados, sem estado extra."""

from dataclasses import dataclass

LEVELS = [(0, "Filhote de cofrinho"), (5, "Farejador"), (25, "Caçador"),
          (80, "Mestre das promoções"), (200, "Lenda do desconto")]


@dataclass(frozen=True)
class Stats:
    scans: int = 0            # snapshots de preço + varreduras de busca registradas
    alerts_sent: int = 0      # ofertas avisadas
    best_drop_pct: float = 0  # maior queda vista (preço antigo -> atual)
    tracked: int = 0          # produtos/buscas acompanhados


def xp(s: Stats) -> int:
    return s.scans + s.alerts_sent * 10 + s.tracked * 3


def level(points: int) -> dict:
    idx = max(i for i, (need, _) in enumerate(LEVELS) if points >= need)
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    base = LEVELS[idx][0]
    progress = 1.0 if nxt is None else (points - base) / (nxt - base)
    return {"level": idx + 1, "title": LEVELS[idx][1], "xp": points,
            "next_at": nxt, "progress": round(progress, 3)}


def achievements(s: Stats) -> list[dict]:
    rules = [
        ("primeira-pista", "Primeira pista", "Acompanhe seu primeiro produto ou busca", s.tracked >= 1),
        ("farejador", "Faro apurado", "10 coletas de preço registradas", s.scans >= 10),
        ("achou", "Achou barato!", "Receba seu primeiro alerta de oferta", s.alerts_sent >= 1),
        ("queda-20", "Queda de respeito", "Veja uma queda de 20% ou mais", s.best_drop_pct >= 20),
        ("persistente", "Persistente", "100 coletas registradas", s.scans >= 100),
    ]
    return [{"id": i, "title": t, "description": d, "unlocked": ok} for i, t, d, ok in rules]
