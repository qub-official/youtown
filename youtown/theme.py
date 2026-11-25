"""Palette, stylesheet and icons. Soft editorial look: white/sand paper, ink text, gold + mauve accents."""
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

WHITE = "#FFFFFF"
CREAM = "#F5F4F2"
SAND = "#E9E4E0"
NUDE = "#EEE5E0"
INK = "#0C0F14"
BLACK = "#000000"
GRAY = "#2E2F33"
GOLD = "#A87C3A"
MAUVE = "#B08A8A"
BUTTER = "#FDEBB0"
TAUPE = "#B49A85"
MUTED = "#7F756D"  # warm gray derived from taupe, for secondary text with good contrast

SERIF = "Georgia"
SANS = "Segoe UI Variable Text"

TYPE_BG = {"video": SAND, "audio": NUDE, "image": CREAM}

QSS = f"""
* {{ font-family: "{SANS}", "Segoe UI"; font-size: 13px; color: {INK}; outline: none; }}
QMainWindow, #Root, #LibraryPage, #SettingsPage, #SettingsInner {{ background: {WHITE}; }}
QToolTip {{ background: {INK}; color: {WHITE}; border: none; padding: 5px 9px; border-radius: 6px; }}

#Sidebar {{ background: {CREAM}; border-right: 1px solid {SAND}; }}
#Brand {{ font-family: "{SERIF}"; font-size: 23px; font-style: italic; color: {INK}; }}
#BrandDot {{ color: {GOLD}; font-family: "{SERIF}"; font-size: 23px; }}
#Tagline {{ color: {TAUPE}; font-size: 11px; letter-spacing: 1px; }}
QPushButton#Nav {{ text-align: left; padding: 9px 12px; border: none; border-radius: 12px; color: {GRAY}; background: transparent; }}
QPushButton#Nav:hover {{ background: {NUDE}; }}
QPushButton#Nav:checked {{ background: {WHITE}; color: {INK}; font-weight: 600; border: 1px solid {SAND}; }}
#Count {{ color: {TAUPE}; font-size: 11px; background: transparent; }}
#SectionLabel {{ color: {TAUPE}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}

#PageTitle {{ font-family: "{SERIF}"; font-size: 30px; color: {INK}; }}
#PageSub {{ color: {MUTED}; font-size: 12px; }}
#Eyebrow {{ color: {GOLD}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}

QLineEdit {{ background: {CREAM}; border: 1px solid {SAND}; border-radius: 17px; padding: 7px 14px; selection-background-color: {BUTTER}; selection-color: {INK}; }}
QLineEdit:focus {{ border-color: {MAUVE}; background: {WHITE}; }}
QLineEdit#Search {{ padding-left: 34px; }}

QComboBox {{ background: {CREAM}; border: 1px solid {SAND}; border-radius: 17px; padding: 7px 14px; min-width: 90px; }}
QComboBox:hover {{ border-color: {TAUPE}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {WHITE}; border: 1px solid {SAND}; selection-background-color: {NUDE}; selection-color: {INK}; padding: 4px; }}

QToolButton {{ border: none; border-radius: 12px; padding: 6px; background: transparent; }}
QToolButton:hover {{ background: {NUDE}; }}
QToolButton:checked {{ background: {BUTTER}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#Play {{ background: {INK}; border-radius: 23px; }}
QToolButton#Play:hover {{ background: {GRAY}; }}
QToolButton#Pill {{ background: {CREAM}; border: 1px solid {SAND}; border-radius: 13px; padding: 3px 10px; font-size: 12px; font-weight: 600; color: {GRAY}; }}
QToolButton#Pill:hover {{ border-color: {TAUPE}; }}
QToolButton#Seg {{ border-radius: 10px; padding: 5px; }}
QToolButton#Seg:checked {{ background: {WHITE}; border: 1px solid {SAND}; }}
#SegBox {{ background: {CREAM}; border: 1px solid {SAND}; border-radius: 13px; }}

QPushButton {{ background: {CREAM}; border: 1px solid {SAND}; border-radius: 17px; padding: 8px 18px; color: {INK}; }}
QPushButton:hover {{ background: {NUDE}; border-color: {TAUPE}; }}
QPushButton#Primary {{ background: {INK}; color: {WHITE}; border: 1px solid {INK}; border-radius: 17px; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {GRAY}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {MUTED}; }}
QPushButton#Ghost:hover {{ color: {INK}; text-decoration: underline; }}

QSlider::groove:horizontal {{ height: 4px; background: {SAND}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {GOLD}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -5px 0; border-radius: 7px; background: {WHITE}; border: 2px solid {GOLD}; }}
QSlider::handle:horizontal:hover {{ background: {BUTTER}; }}
QSlider#Volume::sub-page:horizontal {{ background: {MAUVE}; }}
QSlider#Volume::handle:horizontal {{ border-color: {MAUVE}; }}

#PlayerBar {{ background: {WHITE}; border-top: 1px solid {SAND}; }}
#NowTitle {{ font-weight: 600; font-size: 13px; }}
#NowSub {{ color: {MUTED}; font-size: 12px; }}
#Time {{ color: {MUTED}; font-size: 11px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {SAND}; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {TAUPE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QMenu {{ background: {WHITE}; border: 1px solid {SAND}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 26px; border-radius: 8px; color: {INK}; }}
QMenu::item:selected {{ background: {NUDE}; }}
QMenu::item:disabled {{ color: {TAUPE}; }}
QMenu::separator {{ height: 1px; background: {SAND}; margin: 5px 10px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 7px; }}
QMenu::right-arrow {{ width: 8px; right: 8px; }}

QListView#Library {{ background: {WHITE}; border: none; }}
QListWidget#Queue {{ background: {CREAM}; border: none; padding: 4px; }}
QListWidget#Queue::item {{ padding: 8px 10px; border-radius: 10px; color: {GRAY}; }}
QListWidget#Queue::item:hover {{ background: {NUDE}; }}
QListWidget#Queue::item:selected {{ background: {WHITE}; color: {INK}; }}
#QueuePanel {{ background: {CREAM}; border-left: 1px solid {SAND}; }}
#ScanBar {{ background: {CREAM}; border-bottom: 1px solid {SAND}; }}
#ScanText {{ color: {MUTED}; font-size: 11px; }}

#Card {{ background: {WHITE}; border: 1px solid {SAND}; border-radius: 18px; }}
#CardTitle {{ font-family: "{SERIF}"; font-size: 18px; }}
#Hint {{ color: {MUTED}; }}
#Status {{ color: {GRAY}; background: {CREAM}; border-radius: 12px; padding: 8px 12px; }}
#FolderRow {{ background: {CREAM}; border-radius: 12px; }}
#Kbd {{ background: {CREAM}; border: 1px solid {SAND}; border-bottom: 2px solid {SAND}; border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 600; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 36px; height: 20px; border-radius: 10px; background: {SAND}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; }}

#PlayerTop {{ background: {INK}; }}
#PlayerTop QLabel {{ color: {CREAM}; }}
#PlayerTop QToolButton:hover {{ background: #2A2D33; }}
#VideoSurface, #ImageView {{ background: {INK}; }}
#Toast {{ background: {INK}; color: {WHITE}; border-radius: 16px; padding: 9px 18px; font-size: 12px; }}
#Mini {{ background: {INK}; }}
#MiniStrip {{ background: {WHITE}; }}
#MiniTitle {{ font-weight: 600; font-size: 12px; }}
#MiniSub {{ color: {MUTED}; font-size: 11px; }}
QToolButton#MiniPlay {{ background: {INK}; border-radius: 18px; }}
QToolButton#MiniPlay:hover {{ background: {GRAY}; }}
QSlider#MiniSeek::groove:horizontal {{ height: 3px; background: {SAND}; border-radius: 1px; }}
QSlider#MiniSeek::sub-page:horizontal {{ background: {GOLD}; border-radius: 1px; }}
QSlider#MiniSeek::handle:horizontal {{ width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; background: {GOLD}; border: none; }}
#EmptyTitle {{ font-family: "{SERIF}"; font-size: 22px; }}
"""

# 24x24 line icons (stroke) and a few solid ones.
_ICONS = {
    "all": '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
    "video": '<rect x="2.5" y="5.5" width="14" height="13" rx="3"/><path d="M16.5 10.5l5-3v9l-5-3z"/>',
    "audio": '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.8"/><path d="M21 15l-5-5L5 21"/>',
    "recent": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "folder": '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.2h7.5A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>',
    "open": '<path d="M14 3H6.5A2.5 2.5 0 0 0 4 5.5v13A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V9z"/><path d="M14 3v6h6M12 12v6M9 15h6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "settings": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r=".8"/><circle cx="4.5" cy="12" r=".8"/><circle cx="4.5" cy="18" r=".8"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    "full": '<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/>',
    "unfull": '<path d="M9 4v3.5A1.5 1.5 0 0 1 7.5 9H4M15 4v3.5A1.5 1.5 0 0 0 16.5 9H20M20 15h-3.5a1.5 1.5 0 0 0-1.5 1.5V20M4 15h3.5A1.5 1.5 0 0 1 9 16.5V20"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "more": '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    "queue": '<path d="M4 6h12M4 11h12M4 16h7"/><path d="M16 14v6l5-3z"/>',
    "screen": '<rect x="3" y="4" width="18" height="13" rx="3"/><path d="M8 21h8M12 17v4"/>',
    "shuffle": '<path d="M16 4h4v4M4 20L20 4M20 16v4h-4M15 15l5 5M4 4l5 5"/>',
    "repeat": '<path d="M17 2l3 3-3 3"/><path d="M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3"/><path d="M20 13v2a4 4 0 0 1-4 4H4"/>',
    "repeat1": '<path d="M17 2l3 3-3 3"/><path d="M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3"/><path d="M20 13v2a4 4 0 0 1-4 4H4"/><path d="M11 10l1.5-1v6"/>',
    "vol": '<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
    "volLow": '<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>',
    "volX": '<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M16 9l6 6M22 9l-6 6"/>',
    "trash": '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    "camera": '<path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.8l1.5-2h4.4l1.5 2h1.8A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.5"/>',
    "mini": '<rect x="2.5" y="4.5" width="19" height="15" rx="3"/><rect x="12" y="11.5" width="7" height="5.5" rx="1.4"/>',
    "pin": '<path d="M9 3h6l-1 6 4 3v2H6v-2l4-3z"/><path d="M12 14v7"/>',
    "expand": '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
    "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
    # solid
    "play": 'S<path d="M7 4.6v14.8a1 1 0 0 0 1.52.85l12.1-7.4a1 1 0 0 0 0-1.7L8.52 3.75A1 1 0 0 0 7 4.6z"/>',
    "pause": 'S<rect x="5.5" y="4" width="4.5" height="16" rx="1.4"/><rect x="14" y="4" width="4.5" height="16" rx="1.4"/>',
    "next": 'S<path d="M5 5.6v12.8a1 1 0 0 0 1.53.85l9.6-6.4a1 1 0 0 0 0-1.7l-9.6-6.4A1 1 0 0 0 5 5.6z"/><rect x="16.5" y="4.5" width="2.8" height="15" rx="1.3"/>',
    "prev": 'S<path d="M19 5.6v12.8a1 1 0 0 1-1.53.85l-9.6-6.4a1 1 0 0 1 0-1.7l9.6-6.4A1 1 0 0 1 19 5.6z"/><rect x="4.7" y="4.5" width="2.8" height="15" rx="1.3"/>',
    "stop": 'S<rect x="5" y="5" width="14" height="14" rx="2.5"/>',
}

_cache = {}


def _dpr():
    app = QGuiApplication.instance()
    return app.primaryScreen().devicePixelRatio() if app and app.primaryScreen() else 1.0


def svg_image(name, color, px) -> QImage:
    body = _ICONS[name]
    if body.startswith("S"):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}">{body[1:]}</svg>'
    else:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, px, px))
    p.end()
    return img


def pixmap(name, color=GRAY, size=20) -> QPixmap:
    key = (name, color, size)
    if key not in _cache:
        dpr = _dpr()
        pm = QPixmap.fromImage(svg_image(name, color, round(size * dpr)))
        pm.setDevicePixelRatio(dpr)
        _cache[key] = pm
    return _cache[key]


def icon(name, color=GRAY, size=20, active=None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Normal)
    if active:
        ic.addPixmap(pixmap(name, active, size), QIcon.Active)
    return ic


def app_icon_image(size: int) -> QImage:
    """Rounded nude-to-mauve tile, soft white play, a little gold sparkle."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    tile = QPainterPath()
    m = s * 0.04
    tile.addRoundedRect(QRectF(m, m, s - 2 * m, s - 2 * m), s * 0.25, s * 0.25)
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, QColor(NUDE))
    g.setColorAt(1, QColor(MAUVE))
    p.fillPath(tile, g)
    tri = QPainterPath()
    tri.moveTo(s * 0.40, s * 0.31)
    tri.lineTo(s * 0.40, s * 0.69)
    tri.lineTo(s * 0.71, s * 0.50)
    tri.closeSubpath()
    pen = QPen(QColor(WHITE), s * 0.07, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QColor(WHITE))
    p.drawPath(tri)
    # sparkle
    cx, cy, r = s * 0.74, s * 0.25, s * 0.085
    star = QPainterPath()
    star.moveTo(cx, cy - r)
    for a, b in ((cx + r * 0.25, cy - r * 0.25), (cx + r, cy), (cx + r * 0.25, cy + r * 0.25), (cx, cy + r),
                 (cx - r * 0.25, cy + r * 0.25), (cx - r, cy), (cx - r * 0.25, cy - r * 0.25)):
        star.lineTo(QPointF(a, b))
    star.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BUTTER))
    p.drawPath(star)
    p.end()
    return img


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(QPixmap.fromImage(app_icon_image(s)))
    return ic
