"""Windows integration: Default apps registration, media keys, taskbar buttons and progress."""
import ctypes
import os
import subprocess
import sys
import uuid
import winreg
from ctypes import POINTER, WINFUNCTYPE, Structure, byref, c_void_p, wintypes

from .config import APP_NAME, FROZEN
from .formats import ASSOC

PROGID = "YouTown.Media"
CAP_KEY = r"Software\YouTownPlayer\Capabilities"


# ---------------- default apps ----------------
def open_command():
    if FROZEN:
        return f'"{sys.executable}" "%1"'
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "run.py"))
    return f'"{exe}" "{script}" "%1"'


def icon_ref():
    if FROZEN:
        return f'"{sys.executable}",0'
    ico = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "youtown.ico"))
    return f'"{ico}"' if os.path.exists(ico) else f'"{sys.executable}",0'


def _set(path, name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_tree(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


def _delete_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def _notify():
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def register_default():
    base = rf"Software\Classes\{PROGID}"
    _set(base, "", f"{APP_NAME} media")
    _set(base + r"\DefaultIcon", "", icon_ref())
    _set(base + r"\shell\open", "FriendlyAppName", APP_NAME)
    _set(base + r"\shell\open\command", "", open_command())
    _set(CAP_KEY, "ApplicationName", APP_NAME)
    _set(CAP_KEY, "ApplicationDescription", "Plays your videos, music and images.")
    _set(CAP_KEY, "ApplicationIcon", icon_ref())
    for e in ASSOC:
        _set(rf"Software\Classes\.{e}\OpenWithProgids", PROGID, "")
        _set(CAP_KEY + r"\FileAssociations", "." + e, PROGID)
    _set(r"Software\RegisteredApplications", APP_NAME, CAP_KEY)
    _notify()


def unregister_default():
    _delete_tree(rf"Software\Classes\{PROGID}")
    _delete_tree(r"Software\YouTownPlayer")
    _delete_value(r"Software\RegisteredApplications", APP_NAME)
    for e in ASSOC:
        _delete_value(rf"Software\Classes\.{e}\OpenWithProgids", PROGID)
    _notify()


def default_status():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}\shell\open\command") as k:
            cmd = winreg.QueryValueEx(k, "")[0]
        return "registered" if cmd == open_command() else "stale"
    except OSError:
        return "none"


def open_default_apps():
    os.startfile("ms-settings:defaultapps?registeredAppUser=" + APP_NAME.replace(" ", "%20"))


def show_in_explorer(path):
    subprocess.Popen(f'explorer /select,"{path}"')


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]


def show_properties(path):
    """Open the Windows file Properties dialog (location, size, dates, details)."""
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x0000000C  # SEE_MASK_INVOKEIDLIST
    info.lpVerb = "properties"
    info.lpFile = path
    info.nShow = 1
    ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))


def system_light_theme():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


# ---------------- media keys ----------------
WM_HOTKEY = 0x0312
MEDIA_KEYS = {1: 0xB3, 2: 0xB0, 3: 0xB1, 4: 0xB2}  # play/pause, next, prev, stop
user32 = ctypes.WinDLL("user32")


def register_media_keys(hwnd):
    ok = []
    for hid, vk in MEDIA_KEYS.items():
        if user32.RegisterHotKey(wintypes.HWND(hwnd), hid, 0x4000, vk):
            ok.append(hid)
    return ok


def unregister_media_keys(hwnd):
    for hid in MEDIA_KEYS:
        user32.UnregisterHotKey(wintypes.HWND(hwnd), hid)


# ---------------- taskbar (ITaskbarList3) ----------------
class GUID(Structure):
    _fields_ = [("b", ctypes.c_ubyte * 16)]

    def __init__(self, s):
        super().__init__()
        ctypes.memmove(byref(self), uuid.UUID(s).bytes_le, 16)


class THUMBBUTTON(Structure):
    _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT), ("iBitmap", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 260), ("dwFlags", wintypes.DWORD)]


class ICONINFO(Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


class BITMAPINFOHEADER(Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


WM_COMMAND = 0x0111
THBN_CLICKED = 0x1800
TBPF_NOPROGRESS, TBPF_NORMAL, TBPF_PAUSED = 0, 2, 8
TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarButtonCreated")

gdi32 = ctypes.WinDLL("gdi32")
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, c_void_p, wintypes.UINT, POINTER(c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.CreateIconIndirect.restype = wintypes.HICON
user32.CreateIconIndirect.argtypes = [POINTER(ICONINFO)]


def hicon_from_qimage(img):
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0)
    bits = c_void_p()
    hbm = gdi32.CreateDIBSection(None, byref(bih), 0, byref(bits), None, 0)
    data = bytes(img.constBits())[: w * h * 4]
    ctypes.memmove(bits, data, len(data))
    mask = gdi32.CreateBitmap(w, h, 1, 1, None)
    ii = ICONINFO(True, 0, 0, mask, hbm)
    hicon = user32.CreateIconIndirect(byref(ii))
    gdi32.DeleteObject(hbm)
    gdi32.DeleteObject(mask)
    return hicon


class Taskbar:
    def __init__(self, hwnd):
        self.hwnd = wintypes.HWND(hwnd)
        self.ptr = c_void_p()
        self.added = False
        try:
            ole32 = ctypes.OleDLL("ole32")
            ole32.CoCreateInstance(byref(GUID("56FDF344-FD6D-11d0-958A-006097C9A090")), None, 1,
                                   byref(GUID("ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf")), byref(self.ptr))
            self.vtbl = ctypes.cast(self.ptr, POINTER(POINTER(c_void_p)))[0]
            self._call(3, [])  # HrInit
        except OSError:
            self.ptr = None

    def _call(self, index, argtypes, *args):
        fn = WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(self.vtbl[index])
        return fn(self.ptr, *args)

    def progress(self, value, total, paused=False):
        if not self.ptr:
            return
        try:
            if total <= 0:
                self._call(10, [wintypes.HWND, ctypes.c_int], self.hwnd, TBPF_NOPROGRESS)
                return
            self._call(10, [wintypes.HWND, ctypes.c_int], self.hwnd, TBPF_PAUSED if paused else TBPF_NORMAL)
            self._call(9, [wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong], self.hwnd, int(value), int(total))
        except OSError:
            pass

    def set_buttons(self, buttons):
        """buttons: list of (id, hicon, tooltip, enabled)."""
        if not self.ptr:
            return
        arr = (THUMBBUTTON * len(buttons))()
        for i, (bid, hicon, tip, enabled) in enumerate(buttons):
            arr[i].dwMask = 0x2 | 0x4 | 0x8
            arr[i].iId = bid
            arr[i].hIcon = hicon
            arr[i].szTip = tip
            arr[i].dwFlags = 0 if enabled else 1
        try:
            idx = 16 if self.added else 15
            self._call(idx, [wintypes.HWND, wintypes.UINT, POINTER(THUMBBUTTON)], self.hwnd, len(buttons), arr)
            self.added = True
        except OSError:
            pass
