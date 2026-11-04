"""Casamento de termos da busca ("ssd nvme 1tb") com o texto de um produto."""

import re

_CAP_TOKEN = re.compile(r"^\d+(?:[.,]\d+)?(?:tb|gb)$")
# termos da busca que o texto pode expressar de outro jeito
_SYNONYMS = {
    "nvme": ("nvme", "m-2", "m.2"),
    "m2": ("m-2", "m.2", "m2"),
    "m.2": ("m-2", "m.2", "m2"),
    "sata": ("sata",),
}


def matches_terms(haystack: str, queries: list[str]) -> bool:
    """True se, para ao menos uma das buscas, todos os termos não numéricos (fora "ssd")
    aparecem no texto. A capacidade é checada à parte (mínimo de GB)."""
    text = haystack.lower()
    for query in queries:
        tokens = [t for t in query.lower().split() if t != "ssd" and not _CAP_TOKEN.match(t)]
        if all(any(alt in text for alt in _SYNONYMS.get(t, (t,))) for t in tokens):
            return True
    return False
