import logging
from pathlib import Path
from config import config

log = logging.getLogger(__name__)

ZONE_SUBDIRS = ["events", "users", "orders"]   # one subfolder per entity

def init_lakehouse(reset: bool = False):
    """
    Create medallion folder structure.
    If reset=True, wipe existing data (for benchmarking fresh starts).
    """
    import shutil

    zones = [config.bronze_path, config.silver_path, config.gold_path, config.meta_path]

    if reset:
        if config.data_root.exists():
            shutil.rmtree(config.data_root)
            log.warning(f"Wiped {config.data_root}")

    for zone in zones:
        for entity in ZONE_SUBDIRS:
            (zone / entity).mkdir(parents=True, exist_ok=True)
            log.info(f"Created {zone / entity}")

    # Create a .gitkeep so git tracks empty dirs
    for zone in zones:
        for entity in ZONE_SUBDIRS:
            (zone / entity / ".gitkeep").touch()

    log.info("Lakehouse initialized.")


if __name__ == "__main__":
    logging.basicConfig(level=config.log_level)
    init_lakehouse()
