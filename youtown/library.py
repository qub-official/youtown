import json
import os
import re
import time

from PySide6.QtCore import QThread, Signal

from .config import DATA_DIR, LIBRARY_FILE
from .formats import AMBIGUOUS_MIN_SIZE, LIBRARY, ext_of, type_of

SKIP_DIRS = {
    "node_modules", "appdata", "windows", "program files", "program files (x86)", "programdata",
    "system volume information", "venv", "__pycache__", "site-packages", "bower_components",
}


class Item:
    __slots__ = ("path", "name", "ext", "type", "size", "mtime", "dir", "root", "url", "_key")

    def __init__(self, path, size=0, mtime=0.0, root="", url=False):
        self.path = path
        self.url = url
        if url:
            self.name = path.rstrip("/").rsplit("/", 1)[-1] or path
            self.ext = ""
            self.type = "video"
            self.dir = path
        else:
            self.name = os.path.basename(path)
            self.ext = ext_of(path)
            self.type = type_of(path) or "video"
            self.dir = os.path.dirname(path)
        self.size = size
        self.mtime = mtime
        self.root = root or self.dir
        self._key = None

    @property
    def title(self):
        if self.url:
            return self.name
        i = self.name.rfind(".")
        return self.name[:i] if i > 0 else self.name

    @property
    def natural_key(self):
        if self._key is None:
            self._key = [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", self.name.casefold())]
        return self._key

    @classmethod
    def from_path(cls, path, root=""):
        try:
            st = os.stat(path)
        except OSError:
            return None
        return cls(os.path.normpath(path), st.st_size, st.st_mtime, root)

    @classmethod
    def from_url(cls, url):
        return cls(url, url=True)


def _accept(name, size):
    e = ext_of(name)
    if e not in LIBRARY:
        return False
    need = AMBIGUOUS_MIN_SIZE.get(e)
    return need is None or size >= need


def scan_dir(root, out, seen, on_progress=None, accept_all=False, should_stop=None):
    """Iterative walk; os.scandir gives size/mtime for free on Windows."""
    stack = [root]
    while stack:
        if should_stop and should_stop():
            return
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                n = e.name
                if n[0] in ".$":
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if n.lower() not in SKIP_DIRS:
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        st = e.stat(follow_symlinks=False)
                        if (accept_all and type_of(n)) or _accept(n, st.st_size):
                            key = e.path.lower()
                            if key not in seen:
                                seen.add(key)
                                out.append(Item(e.path, st.st_size, st.st_mtime, root))
                except OSError:
                    continue
        if on_progress:
            on_progress(len(out), d)


class Scanner(QThread):
    progress = Signal(int, str)
    partial = Signal(list)
    done = Signal(list)

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = list(folders)
        self._last = 0.0
        self._last_partial = 0.0

    def run(self):
        out, seen = [], set()

        def tick(count, d):
            now = time.monotonic()
            if now - self._last > 0.15:
                self._last = now
                self.progress.emit(count, d)
            if now - self._last_partial > 1.0:
                self._last_partial = now
                self.partial.emit(list(out))

        for f in self.folders:
            scan_dir(f, out, seen, tick, should_stop=self.isInterruptionRequested)
        if self.isInterruptionRequested():
            return
        save_library(out)
        self.done.emit(out)


def load_library():
    try:
        rows = json.loads(LIBRARY_FILE.read_text("utf-8"))
        return [Item(p, s, m, r) for p, s, m, r in rows]
    except Exception:
        return None


def save_library(items):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LIBRARY_FILE.write_text(json.dumps([[i.path, i.size, i.mtime, i.root] for i in items]), "utf-8")
    except Exception:
        pass


def parse_playlist(path):
    """Read m3u/m3u8/pls/xspf into a list of local paths and URLs."""
    e = ext_of(path)
    base = os.path.dirname(path)
    entries = []
    try:
        raw = open(path, "rb").read()
        text = raw.decode("utf-8-sig") if e != "m3u" else raw.decode("utf-8-sig", "replace")
    except (OSError, UnicodeDecodeError):
        try:
            text = open(path, encoding="cp1252", errors="replace").read()
        except OSError:
            return []
    if e in ("m3u", "m3u8"):
        entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    elif e == "pls":
        entries = [ln.split("=", 1)[1].strip() for ln in text.splitlines() if re.match(r"(?i)^file\d+=", ln)]
    elif e == "xspf":
        import xml.etree.ElementTree as ET
        from urllib.parse import unquote, urlparse
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        for loc in root.iter():
            if loc.tag.endswith("location") and loc.text:
                u = loc.text.strip()
                if u.startswith("file:"):
                    pu = urlparse(u)
                    u = unquote(pu.path.lstrip("/") if re.match(r"^/[A-Za-z]:", pu.path) else (("//" + pu.netloc) if pu.netloc else "") + pu.path)
                entries.append(u)
    out = []
    for en in entries:
        if "://" in en:
            out.append(en)
        else:
            out.append(os.path.normpath(en if os.path.isabs(en) else os.path.join(base, en)))
    return out


PARSED_PLAYLISTS = {"m3u", "m3u8", "pls", "xspf"}


def items_from_paths(paths, _depth=0):
    """Expand files, folders (recursively) and playlists into playable items, keeping order."""
    out, seen = [], set()
    for p in paths:
        if "://" in p and not p.lower().startswith("file:"):
            out.append(Item.from_url(p))
            continue
        if ext_of(p) in PARSED_PLAYLISTS and os.path.isfile(p) and _depth < 3:
            out += items_from_paths(parse_playlist(p), _depth + 1)
            continue
        if os.path.isdir(p):
            sub = []
            scan_dir(p, sub, seen, accept_all=True)
            sub.sort(key=lambda i: i.natural_key)
            out += sub
        elif os.path.isfile(p) and p.lower() not in seen:
            it = Item.from_path(p)
            if it:
                seen.add(p.lower())
                out.append(it)
    return out
