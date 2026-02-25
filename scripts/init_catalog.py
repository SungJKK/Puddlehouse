import sqlite3
from pathlib import Path
from config import config

def init_catalog():
    config.catalog_path.parent.mkdir(parents=True, exist_ok=True)
    schema = (Path(__file__).parent / ".." / "catalog" / "schema.sql").read_text()
    con = sqlite3.connect(config.catalog_path)
    con.executescript(schema)
    con.commit()
    con.close()
    print(f"Catalog initialized at {config.catalog_path}")

if __name__ == "__main__":
    init_catalog()
