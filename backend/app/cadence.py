"""Cadência entre varreduras: lista de minutos que se repete (ex.: "60", ou "30,50,60"),
sempre com alguns minutos aleatórios a mais para não ficar num horário exato."""

import random
from itertools import cycle

DEFAULT_CYCLE = (60,)


class Cadence:
    def __init__(self, minutes: tuple[int, ...] = DEFAULT_CYCLE, jitter_seconds: int = 300):
        if not minutes or any(m <= 0 for m in minutes):
            raise ValueError("ciclo precisa de minutos positivos")
        self._cycle = cycle(minutes)
        self._jitter = jitter_seconds

    def next_delay_seconds(self) -> float:
        base = next(self._cycle) * 60
        return base + random.uniform(0, self._jitter)


def parse_cycle(value: str) -> tuple[int, ...]:
    return tuple(int(p) for p in value.split(",") if p.strip())
