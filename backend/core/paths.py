import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    return project_root() / "config"


def resources_dir() -> Path:
    return project_root() / "resources"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def settings_example_path() -> Path:
    return config_dir() / "settings.example.json"


def legacy_settings_path() -> Path:
    return resources_dir() / "conf" / "settings.json"


def database_path() -> Path:
    return resources_dir() / "pixiv.db"
