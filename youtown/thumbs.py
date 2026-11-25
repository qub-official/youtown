"""Thumbnails from the Windows shell (same ones File Explorer shows), cached on disk."""
import ctypes
import hashlib
import threading
import uuid
from collections import OrderedDict, deque
from ctypes import POINTER, WINFUNCTYPE, Structure, byref, c_long, c_void_p, wintypes

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap

from .config import THUMB_DIR

ole32 = ctypes.OleDLL("ole32")
shell32 = ctypes.OleDLL("shell32")
gdi32 = ctypes.WinDLL("gdi32")
user32 = ctypes.WinDLL("user32")


class GUID(Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        super().__init__()
        ctypes.memmove(byref(self), uuid.UUID(s).bytes_le, 16)


class SIZE(Structure):
    _fields_ = [("cx", c_long), ("cy", c_long)]


class BITMAP(Structure):
    _fields_ = [("bmType", c_long), ("bmWidth", c_long), ("bmHeight", c_long), ("bmWidthBytes", c_long),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD), ("bmBits", c_void_p)]


class BITMAPINFOHEADER(Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", c_long), ("biHeight", c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", c_long), ("biYPelsPerMeter", c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


IID_IShellItemImageFactory = GUID("bcc18b79-ba16-442f-80c4-8a59c30c463b")
shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, c_void_p, POINTER(GUID), POINTER(c_void_p)]
GetImage = WINFUNCTYPE(ctypes.HRESULT, c_void_p, SIZE, ctypes.c_int, POINTER(wintypes.HBITMAP))
Release = WINFUNCTYPE(ctypes.c_ulong, c_void_p)
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, c_void_p]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, c_void_p, c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

SIIGBF_BIGGERSIZEOK = 0x1
SIIGBF_THUMBNAILONLY = 0x8


def shell_thumbnail(path: str, size: int = 320) -> QImage | None:
    ptr = c_void_p()
    try:
        shell32.SHCreateItemFromParsingName(path, None, byref(IID_IShellItemImageFactory), byref(ptr))
    except OSError:
        return None
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
    hbm = wintypes.HBITMAP()
    try:
        GetImage(vtbl[3])(ptr, SIZE(size, size), SIIGBF_THUMBNAILONLY | SIIGBF_BIGGERSIZEOK, byref(hbm))
    except OSError:
        return None
    finally:
        Release(vtbl[2])(ptr)
    try:
        bm = BITMAP()
        gdi32.GetObjectW(hbm, ctypes.sizeof(bm), byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = user32.GetDC(None)
        gdi32.GetDIBits(hdc, hbm, 0, h, buf, byref(bih), 0)
        user32.ReleaseDC(None, hdc)
        raw = buf.raw
        has_alpha = any(raw[3::4])
        fmt = QImage.Format_ARGB32_Premultiplied if has_alpha else QImage.Format_RGB32
        return QImage(raw, w, h, w * 4, fmt).copy()
    finally:
        gdi32.DeleteObject(hbm)


def is_image(path):
    from .formats import IMAGE, ext_of
    return ext_of(path) in IMAGE


def qt_thumbnail(path, size=320):
    """Fallback when Windows has no thumbnail yet: decode the image ourselves, scaled while reading."""
    from PySide6.QtGui import QImageReader
    r = QImageReader(path)
    r.setAutoTransform(True)
    s = r.size()
    if s.isValid() and (s.width() > size or s.height() > size):
        r.setScaledSize(s.scaled(size, size, Qt.KeepAspectRatio))
    img = r.read()
    return None if img.isNull() else img


class ThumbProvider(QObject):
    """get() returns a cached QPixmap or None and fetches missing ones in the background (newest first)."""

    ready = Signal(str)
    _done = Signal(str, QImage)

    def __init__(self, workers=3, parent=None):
        super().__init__(parent)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self._mem = OrderedDict()
        self._failed = set()
        self._pending = set()
        self._queue = deque()
        self._cv = threading.Condition()
        self._done.connect(self._on_done, Qt.QueuedConnection)
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def get(self, item):
        if item.url:
            return None
        pm = self._mem.get(item.path)
        if pm is not None:
            self._mem.move_to_end(item.path)
            return pm
        if item.path not in self._failed and item.path not in self._pending:
            with self._cv:
                self._pending.add(item.path)
                self._queue.append((item.path, item.mtime, item.size))
                if len(self._queue) > 400:
                    old = self._queue.popleft()
                    self._pending.discard(old[0])
                self._cv.notify()
        return None

    def _on_done(self, path, img):
        self._pending.discard(path)
        if img.isNull():
            self._failed.add(path)
            return
        self._mem[path] = QPixmap.fromImage(img)
        if len(self._mem) > 1500:
            self._mem.popitem(last=False)
        self.ready.emit(path)

    def _worker(self):
        try:
            ole32.CoInitializeEx(None, 2)
        except OSError:
            pass
        while True:
            with self._cv:
                while not self._queue:
                    self._cv.wait()
                path, mtime, size = self._queue.pop()
            key = hashlib.md5(f"{path}|{mtime}|{size}".encode("utf-8", "surrogatepass")).hexdigest()
            cache = THUMB_DIR / f"{key}.jpg"
            img = QImage()
            if cache.exists():
                img.load(str(cache))
            if img.isNull():
                got = shell_thumbnail(path)
                if (got is None or got.isNull()) and is_image(path):
                    got = qt_thumbnail(path)
                if got is not None and not got.isNull():
                    if got.width() > 320 or got.height() > 320:
                        got = got.scaled(320, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    img = got.convertToFormat(QImage.Format_RGB32)
                    img.save(str(cache), "JPG", 86)
            self._done.emit(path, img if img is not None else QImage())
