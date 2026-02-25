import os
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class LakehouseConfig:
    # Root can be overridden to s3://bucket/ later — this is the scalability hook
    data_root:    Path = field(default_factory=lambda: Path(os.getenv("DATA_ROOT", "./data")))
    catalog_path: Path = field(default_factory=lambda: Path(os.getenv("CATALOG_PATH", "./data/catalog.db")))
    log_level:    str  = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def bronze_path(self) -> Path:
        return self.data_root / "bronze"

    @property
    def silver_path(self) -> Path:
        return self.data_root / "silver"

    @property
    def gold_path(self) -> Path:
        return self.data_root / "gold"

    @property
    def meta_path(self) -> Path:
        return self.data_root / "_metadata"    # for manifest files

# Singleton — import this everywhere
config = LakehouseConfig()
