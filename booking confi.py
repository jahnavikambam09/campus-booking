"""Settings are loaded from config/settings.json, not hard-coded."""
import json
from dataclasses import dataclass
from pathlib import Path

from .models import Resource
from .timeutil import to_minutes

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
CONFIG_FILE = BASE_DIR / "config" / "settings.json"


@dataclass(frozen=True)
class Settings:
    open_min: int
    close_min: int
    roles: tuple
    rooms: dict          # id -> Resource
    demo: dict           # seed-data ingredients


def load_settings(path: Path = CONFIG_FILE) -> Settings:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rooms = {r["id"]: Resource(**r) for r in raw["rooms"]}
    return Settings(
        open_min=to_minutes(raw["open_time"]),
        close_min=to_minutes(raw["close_time"]),
        roles=tuple(raw["roles"]),
        rooms=rooms,
        demo=raw["demo"],
    )


SETTINGS = load_settings()