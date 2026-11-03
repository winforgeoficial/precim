from urllib.parse import urlparse

from app.stores.base import Store
from app.stores.kabum import KabumStore

_STORES: dict[str, Store] = {"www.kabum.com.br": KabumStore()}


def store_for_url(url: str) -> Store | None:
    return _STORES.get(urlparse(url).netloc)
