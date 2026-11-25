"""Writes assets/youtown.ico (PNG-in-ICO, 16-256 px) from the app's drawn icon."""
import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
from youtown.theme import app_icon_image  # noqa: E402

sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
pngs = []
for s in sizes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    app_icon_image(s).save(buf, "PNG")
    pngs.append(bytes(ba))
out = struct.pack("<HHH", 0, 1, len(sizes))
offset = 6 + 16 * len(sizes)
for s, data in zip(sizes, pngs):
    out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
out += b"".join(pngs)
dest = os.path.join(os.path.dirname(__file__), "..", "assets", "youtown.ico")
open(dest, "wb").write(out)
app_icon_image(512).save(os.path.join(os.path.dirname(dest), "youtown.png"))
print("wrote", os.path.abspath(dest))
