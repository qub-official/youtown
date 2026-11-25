# PyInstaller spec: python -m PyInstaller packaging/youtown.spec --noconfirm
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(SPECPATH, "..")))
from youtown.engine import VLC_DIR  # noqa: E402

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
if not VLC_DIR:
    raise SystemExit("VLC (64-bit) must be installed to build: it is bundled into the app.")

# libVLC + playback plugins (VLC's own GUI, streaming-output and muxer plugins are not needed).
SKIP_PLUGIN_DIRS = {"gui", "stream_out", "access_output", "mux", "lua"}
vlc_files = [(str(VLC_DIR / n), "vlc") for n in ("libvlc.dll", "libvlccore.dll")]
for dirpath, dirnames, filenames in os.walk(VLC_DIR / "plugins"):
    rel = os.path.relpath(dirpath, VLC_DIR)
    parts = rel.split(os.sep)
    if len(parts) > 1 and parts[1] in SKIP_PLUGIN_DIRS:
        continue
    for f in filenames:
        if f.endswith(".dll"):
            vlc_files.append((os.path.join(dirpath, f), os.path.join("vlc", rel)))
vlc_files.append((str(VLC_DIR / "COPYING.txt"), "vlc"))

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=vlc_files + [(os.path.join(ROOT, "assets", "youtown.ico"), "assets")],
    hiddenimports=["vlc"],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL",
              "PySide6.QtPdf", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.QtSql",
              "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtConcurrent"],
    noarchive=False,
)

DROP = ("opengl32sw", "qt6quick", "qt6qml", "qt6pdf", "qt6opengl", "qt6virtualkeyboard", "qt6sql", "qt6dbus",
        "qt6test", "d3dcompiler")
DROP_EXACT = {"libcrypto-3-x64.dll", "libssl-3-x64.dll", "libvlc.dylib", "libvlccore.dylib"}
DROP_DIRS = ("plugins/tls", "plugins/networkinformation", "plugins/generic")


def keep(entry):
    dest = entry[0].replace("\\", "/")
    name = os.path.basename(dest).lower()
    if any(k in name for k in DROP) or name in DROP_EXACT or any(d in dest for d in DROP_DIRS):
        return False
    # libVLC lives in vlc/; drop the extra top-level copies the vlc hook adds
    return not (name in ("libvlc.dll", "libvlccore.dll") and "/" not in dest)


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if "translations" not in d[0].replace("\\", "/").split("/")]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="YouTown Player",
    icon=os.path.join(ROOT, "assets", "youtown.ico"),
    console=False,
    version=os.path.join(SPECPATH, "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="YouTown Player", upx=False)
