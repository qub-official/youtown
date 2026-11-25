"""Builds dist/YouTown Player (portable app) and dist/YouTown-Player-Setup-<ver>.exe.

Usage:  .venv\\Scripts\\python packaging\\build.py
Needs: VLC 64-bit installed (it gets bundled), and NSIS (makensis) for the installer.
"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist", "YouTown Player")
PY = sys.executable


def run(*cmd, **kw):
    print(">", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kw)


def find_makensis():
    found = shutil.which("makensis")
    if found:
        return found
    cands = [r"C:\Program Files (x86)\NSIS\makensis.exe", r"C:\Program Files\NSIS\makensis.exe"]
    cands += glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "electron-builder", "Cache", "nsis", "*", "makensis.exe"))
    return next((c for c in cands if os.path.exists(c)), None)


def main():
    run(PY, os.path.join(HERE, "make_icon.py"))
    run(PY, "-m", "PyInstaller", os.path.join(HERE, "youtown.spec"), "--noconfirm",
        "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(ROOT, "build", "pyi"))

    # Pre-build libVLC's plugin cache so the engine starts in ~50 ms instead of ~300 ms.
    vlc_dir = os.path.join(DIST, "_internal", "vlc")
    code = (
        "import os,sys;d=sys.argv[1];os.add_dll_directory(d);"
        "os.environ['PYTHON_VLC_LIB_PATH']=d+r'\\libvlc.dll';"
        "os.environ['PYTHON_VLC_MODULE_PATH']=os.environ['VLC_PLUGIN_PATH']=d+r'\\plugins';"
        "import vlc;vlc.Instance(['--quiet','--reset-plugins-cache']).release()"
    )
    run(PY, "-c", code, vlc_dir)

    from youtown.formats import ASSOC  # noqa: E402
    with open(os.path.join(HERE, "assoc_cleanup.nsh"), "w", encoding="utf-8") as f:
        for e in ASSOC:
            f.write(f'  DeleteRegValue HKCU "Software\\Classes\\.{e}\\OpenWithProgids" "YouTown.Media"\n')

    makensis = find_makensis()
    if not makensis:
        print("NSIS not found: the portable app is in dist/YouTown Player (installer skipped).")
        return
    run(makensis, "/V2", os.path.join(HERE, "installer.nsi"))
    print("Done:", os.path.join(ROOT, "dist"))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main()
