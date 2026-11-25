"""User playlists (any mix of videos, music, images and streams), stored as JSON."""
import json
import os
import time
import uuid

from .config import DATA_DIR

PLAYLISTS_FILE = DATA_DIR / "playlists.json"


class Playlists:
    def __init__(self):
        self.items = []
        try:
            data = json.loads(PLAYLISTS_FILE.read_text("utf-8"))
            self.items = [p for p in data if isinstance(p, dict) and "id" in p]
        except Exception:
            pass

    def save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = PLAYLISTS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, indent=1), "utf-8")
            os.replace(tmp, PLAYLISTS_FILE)
        except Exception:
            pass

    def get(self, pid):
        return next((p for p in self.items if p["id"] == pid), None)

    def unique_name(self, base):
        names = {p["name"].casefold() for p in self.items}
        name, n = base, 2
        while name.casefold() in names:
            name = f"{base} {n}"
            n += 1
        return name

    def create(self, name, paths=()):
        pl = {"id": uuid.uuid4().hex[:10], "name": self.unique_name(name.strip() or "My playlist"),
              "paths": [], "created": time.time()}
        self.items.append(pl)
        self.add(pl["id"], paths)
        self.save()
        return pl

    def rename(self, pid, name):
        pl = self.get(pid)
        if pl and name.strip():
            pl["name"] = name.strip()
            self.save()

    def delete(self, pid):
        self.items = [p for p in self.items if p["id"] != pid]
        self.save()

    def add(self, pid, paths):
        """Append paths; returns how many were new (duplicates are skipped)."""
        pl = self.get(pid)
        if not pl:
            return 0
        have = {p.lower() for p in pl["paths"]}
        added = 0
        for p in paths:
            if p.lower() not in have:
                pl["paths"].append(p)
                have.add(p.lower())
                added += 1
        self.save()
        return added

    def remove(self, pid, path):
        pl = self.get(pid)
        if pl:
            pl["paths"] = [p for p in pl["paths"] if p != path]
            self.save()

    def move(self, pid, path, delta):
        pl = self.get(pid)
        if not pl or path not in pl["paths"]:
            return
        i = pl["paths"].index(path)
        j = max(0, min(len(pl["paths"]) - 1, i + delta))
        pl["paths"].insert(j, pl["paths"].pop(i))
        self.save()

    def export_m3u(self, pid, dest):
        pl = self.get(pid)
        with open(dest, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write(f"#PLAYLIST:{pl['name']}\n")
            for p in pl["paths"]:
                f.write(p + "\n")
