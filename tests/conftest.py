import sqlite3
import pytest
from pathlib import Path

import config as config_module
from catalog.manager import CatalogManager

SCHEMA_PATH = Path(__file__).parent.parent / "catalog" / "schema.sql"


def db_connect(path):
    """Open a SQLite connection with row_factory set (returns dict-like rows)."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


@pytest.fixture()
def catalog(tmp_path, monkeypatch):
    """
    Isolated CatalogManager backed by a fresh tmp SQLite DB.
    config.data_root and config.catalog_path are patched so any code
    that reads the global config singleton uses tmp paths too.
    """
    db_path = tmp_path / "catalog.db"
    data_root = tmp_path / "warehouse"

    monkeypatch.setattr(config_module.config, "catalog_path", db_path)
    monkeypatch.setattr(config_module.config, "data_root", data_root)

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_PATH.read_text())
    con.commit()
    con.close()

    return CatalogManager(catalog_path=db_path)


@pytest.fixture()
def writer_env(catalog, monkeypatch):
    """
    Patches storage.writer's module-level catalog singleton with the isolated
    test catalog, so write_parquet hits the tmp DB and tmp warehouse directory.
    """
    import storage.writer as writer_module
    monkeypatch.setattr(writer_module, "catalog", catalog)
    return catalog
