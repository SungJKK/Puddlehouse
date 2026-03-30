import os
import tomllib
from pathlib import Path
from dataclasses import dataclass

_CONFIG_PATH = Path.home() / ".lh" / "config.toml"
_DEFAULT_API_URL = "http://localhost:8000/api/v1"
_DEFAULT_OUTPUT = "table"


@dataclass
class Config:
    api_url: str
    output: str


def load_config(api_url: str | None = None, output: str | None = None) -> Config:
    """Resolve api_url and output format.

    Precedence (highest to lowest):
      1. Explicit CLI flag value (passed as arguments here)
      2. LH_API_URL / LH_OUTPUT environment variables
      3. ~/.lh/config.toml
      4. Built-in defaults
    """
    file_cfg: dict = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            file_cfg = tomllib.load(f)

    resolved_url = (
        api_url
        or os.environ.get("LH_API_URL")
        or file_cfg.get("api_url")
        or _DEFAULT_API_URL
    )
    resolved_output = (
        output
        or os.environ.get("LH_OUTPUT")
        or file_cfg.get("output")
        or _DEFAULT_OUTPUT
    )

    return Config(api_url=resolved_url.rstrip("/"), output=resolved_output)
