import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "Data"
DEFAULT_SETTINGS_PATH = DEFAULT_DATA_DIR / "settings.csv"


def load_settings(path: str | Path | None = None) -> dict[str, str]:
    """Read flat key,value CSV into a dict of strings."""
    settings_path = Path(path or DEFAULT_SETTINGS_PATH)
    if not settings_path.exists():
        return {}

    settings: dict[str, str] = {}
    with settings_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("key") or "").strip()
            if key:
                settings[key] = (row.get("value") or "").strip()
    return settings


def get_data_dir(settings: dict[str, str] | None = None) -> Path:
    """Return the configured data directory from settings.csv or the default Data folder."""
    if settings is None:
        settings = load_settings()

    data_dir = (settings or {}).get("data_dir", "").strip()
    if data_dir:
        return Path(data_dir).expanduser()
    return DEFAULT_DATA_DIR


def resolve_data_path(filename: str | Path, settings: dict[str, str] | None = None) -> Path:
    """Resolve a file path relative to the configured data directory."""
    target = Path(filename)
    if target.is_absolute():
        return target
    return (get_data_dir(settings) / target).resolve()
