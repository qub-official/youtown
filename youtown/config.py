import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_NAME = "YouTown Player"
VERSION = "2.0.0"

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
THUMB_DIR = CACHE_DIR / "thumbs"
SETTINGS_FILE = DATA_DIR / "youtown.json"
LIBRARY_FILE = DATA_DIR / "library-v2.json"

FROZEN = getattr(sys, "frozen", False)


def default_folders():
    out = []
    for loc in (
        QStandardPaths.MoviesLocation,
        QStandardPaths.MusicLocation,
        QStandardPaths.PicturesLocation,
        QStandardPaths.DownloadLocation,
        QStandardPaths.DesktopLocation,
    ):
        p = QStandardPaths.writableLocation(loc)
        if p and os.path.isdir(p):
            p = os.path.normpath(p)
            if p not in out:
                out.append(p)
    return out


DEFAULTS = {
    "folders": None,
    "volume": 80,
    "muted": False,
    "shuffle": False,
    "repeat": "off",  # off | all | one
    "layout": "grid",
    "sort": "name",
    "close_to_tray": False,
    "media_keys": True,
    "resume": True,
    "slide_interval": 5,
    "recent": [],
    "positions": {},
    "geometry": "",
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            self.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except Exception:
            pass
        if not self.get("folders"):
            self["folders"] = default_folders()

    def save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self, indent=1), "utf-8")
            os.replace(tmp, SETTINGS_FILE)
        except Exception:
            pass
