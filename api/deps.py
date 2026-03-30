from catalog.manager import CatalogManager
from query.engine import QueryEngine

_catalog: CatalogManager | None = None
_engine: QueryEngine | None = None


def init_shared(catalog: CatalogManager, engine: QueryEngine) -> None:
    global _catalog, _engine
    _catalog = catalog
    _engine = engine


def get_catalog() -> CatalogManager:
    return _catalog


def get_engine() -> QueryEngine:
    return _engine
