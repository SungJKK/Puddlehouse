"""
clean_up.py

Removes all files and directories created by scripts/ during lakehouse
initialization and data ingestion. Preserves .gitkeep files so the
directory structure stays tracked in git.

Usage:
    uv run python scripts/clean_up.py           # remove data files + catalog
    uv run python scripts/clean_up.py --all     # also remove top-level data/ dir
"""

import argparse
import shutil
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import config

logging.basicConfig(level=config.log_level, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def _remove_file(path: Path) -> None:
    if path.exists():
        path.unlink()
        log.info(f"Removed file:      {path}")
    else:
        log.debug(f"Already absent:    {path}")


def _clean_dir(path: Path) -> None:
    """Remove all contents of a directory, but keep .gitkeep files and the directory itself."""
    if not path.exists():
        log.debug(f"Already absent:    {path}")
        return
    removed = 0
    for item in path.rglob("*"):
        if item.name == ".gitkeep":
            continue
        if item.is_file():
            item.unlink()
            log.info(f"Removed file:      {item}")
            removed += 1
        elif item.is_dir() and not any(
            True for _ in item.iterdir() if _.name != ".gitkeep"
        ):
            # only remove empty dirs (after their contents are gone)
            pass
    # second pass: remove empty subdirs (excluding those with .gitkeep)
    for item in sorted(path.rglob("*"), reverse=True):
        if item.is_dir() and item != path:
            contents = list(item.iterdir())
            if all(f.name == ".gitkeep" for f in contents) or not contents:
                pass  # keep dirs that hold .gitkeep
            elif not contents:
                item.rmdir()
                log.info(f"Removed empty dir: {item}")
    if removed == 0:
        log.info(f"Already clean:     {path}")


def clean_catalog() -> None:
    """Remove the SQLite catalog file created by init_catalog.py."""
    log.info("--- Cleaning catalog ---")
    _remove_file(config.catalog_path)


def clean_warehouse() -> None:
    """Remove all data files in bronze/silver/gold/_metadata, preserving .gitkeep."""
    log.info("--- Cleaning warehouse data ---")
    for zone in [config.bronze_path, config.silver_path, config.gold_path, config.meta_path]:
        _clean_dir(zone)


def clean_pycache() -> None:
    """Remove __pycache__ directories under scripts/."""
    log.info("--- Cleaning __pycache__ ---")
    scripts_dir = Path(__file__).parent
    for cache_dir in scripts_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir)
        log.info(f"Removed dir:       {cache_dir}")


def clean_all() -> None:
    """Remove the entire data/ directory (catalog + warehouse). Does not preserve .gitkeep."""
    log.info("--- Removing entire data root ---")
    if config.data_root.exists():
        shutil.rmtree(config.data_root)
        log.info(f"Removed dir:       {config.data_root}")
    else:
        log.info(f"Already absent:    {config.data_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up lakehouse-generated files.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also remove the entire data/ directory (implies loss of .gitkeep files).",
    )
    args = parser.parse_args()

    if args.all:
        clean_all()
    else:
        clean_catalog()
        clean_warehouse()

    clean_pycache()
    log.info("Done.")


if __name__ == "__main__":
    main()
