"""Regras puras sobre preço: referência de mercado e suspeita de preço bom demais."""

from statistics import median

SUSPECT_RATIO = 0.5  # R$/GB abaixo de metade da mediana conferida = suspeito
MIN_REFERENCE = 3  # precisa de ao menos 3 ofertas conferidas para ter referência


def reference_ppg(ppgs: list[float]) -> float | None:
    return median(ppgs) if len(ppgs) >= MIN_REFERENCE else None


def is_suspect(ppg: float | None, reference: float | None) -> bool:
    return bool(ppg and reference and ppg < reference * SUSPECT_RATIO)
