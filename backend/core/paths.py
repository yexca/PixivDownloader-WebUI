import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    return project_root() / "resources"


def settings_path() -> Path:
    return resources_dir() / "conf" / "settings.json"


def database_path() -> Path:
    return resources_dir() / "pixiv.db"
