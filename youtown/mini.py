"""Mini player: a small rounded window that stays above other apps. Drag it anywhere, resize from the edges."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QByteArray, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QLinearGradient, QPainter, QPainterPath, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)

from . import theme as T
from .widgets import ClickSlider, ImageView, fmt_time

EDGE = 7
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34


def _btn(icon, tip, color=T.GRAY, size=18, obj=None, checkable=False):
    b = QToolButton()
    b.setIcon(T.icon(icon, color, size, T.INK if color != T.WHITE else T.WHITE))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(checkable)
    if obj:
        b.setObjectName(obj)
    return b


class MiniArt(QWidget):
    """Cover art filling the area (or a soft gradient with a note)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None
        self.setMouseTracking(True)

    def set_art(self, pm):
        if pm is not self.pm:
            self.pm = pm
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect()
        if self.pm is not None and not self.pm.isNull():
            dpr = self.pm.devicePixelRatio() or 1
            pw, ph = self.pm.width() / dpr, self.pm.height() / dpr
            scale = max(r.width() / pw, r.height() / ph)
            sw, sh = r.width() / scale, r.height() / scale
            p.drawPixmap(QRectF(r), self.pm, QRectF((pw - sw) / 2 * dpr, (ph - sh) / 2 * dpr, sw * dpr, sh * dpr))
        else:
            g = QLinearGradient(0, 0, r.width(), r.height())
            g.setColorAt(0, QColor(T.BUTTER))
            g.setColorAt(1, QColor(T.MAUVE))
            p.fillRect(r, g)
            s = max(20, min(r.width(), r.height()) // 4)
            ic = T.pixmap("audio", T.WHITE, s)
            p.drawPixmap(r.center().x() - s // 2, r.center().y() - s // 2, ic)


class MiniPlayer(QWidget):
    def __init__(self, win):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.win = win
        self.setObjectName("Mini")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setWindowTitle("YouTown · mini player")
        self.setWindowIcon(T.app_icon())
        self.setMinimumSize(280, 210)
        self.setMouseTracking(True)
        self.video = None
        self.kind = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setMouseTracking(True)
        self.art = MiniArt()
        self.image = ImageView()
        self.image.setMouseTracking(True)
        self.image.doubleClicked.connect(self.win.exit_mini)
        self.stack.addWidget(self.art)
        self.stack.addWidget(self.image)
        v.addWidget(self.stack, 1)

        strip = QFrame(objectName="MiniStrip")
        strip.setMouseTracking(True)
        sv = QVBoxLayout(strip)
        sv.setContentsMargins(12, 12, 10, 12)
        sv.setSpacing(10)
        self.seek = ClickSlider()
        self.seek.setObjectName("MiniSeek")
        self.seek.setRange(0, 10000)
        self.seek.moved.connect(self.win._seek_to)
        sv.addWidget(self.seek)
        row = QHBoxLayout()
        row.setSpacing(2)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = QLabel("", objectName="MiniTitle")
        self.sub = QLabel("", objectName="MiniSub")
        for l in (self.title, self.sub):
            l.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            l.setMouseTracking(True)
            texts.addWidget(l)
        row.addLayout(texts, 1)
        row.addSpacing(6)
        self.b_prev = _btn("prev", "Previous (P)", T.INK, 16)
        self.b_play = _btn("play", "Play (Space)", T.WHITE, 15, obj="MiniPlay")
        self.b_play.setFixedSize(36, 36)
        self.b_next = _btn("next", "Next (N)", T.INK, 16)
        self.b_prev.clicked.connect(self.win.prev)
        self.b_play.clicked.connect(self.win.toggle_play)
        self.b_next.clicked.connect(self.win.next)
        for b in (self.b_prev, self.b_play, self.b_next):
            row.addWidget(b)
        row.addSpacing(8)
        self.b_pin = _btn("pin", "Keep on top", T.MUTED, 16, checkable=True)
        self.b_pin.setChecked(True)
        self.b_pin.toggled.connect(self.set_on_top)
        self.b_full = _btn("expand", "Back to full window (Esc)", T.GRAY, 16)
        self.b_full.clicked.connect(self.win.exit_mini)
        self.b_close = _btn("x", "Close mini player", T.GRAY, 16)
        self.b_close.clicked.connect(self.win.exit_mini)
        for b in (self.b_pin, self.b_full, self.b_close):
            row.addWidget(b)
        sv.addLayout(row)
        v.addWidget(strip)

        keys = {"Space": self.win.toggle_play, "N": self.win.next, "P": self.win.prev, "M": self.win.toggle_mute,
                "Escape": self.win.exit_mini, "Right": lambda: self.win.jump(10_000),
                "Left": lambda: self.win.jump(-10_000), "Up": lambda: self.win.nudge_volume(5),
                "Down": lambda: self.win.nudge_volume(-5)}
        for k, fn in keys.items():
            QShortcut(QKeySequence(k), self, activated=fn)

        self.timer = QTimer(self, interval=250, timeout=self.refresh)
        self._last_playing = None

    # ---------------------------------------------------------- content
    def attach_video(self, video):
        """Move the native VLC surface in here (same HWND, so playback never restarts)."""
        if self.video is video:
            return
        self.video = video
        self.stack.insertWidget(0, video)
        video.setMouseTracking(True)

    def detach_video(self):
        v, self.video = self.video, None
        if v is not None:
            self.stack.removeWidget(v)
        return v

    def set_kind(self, kind):
        self.kind = kind
        if kind == "video" and self.video is not None:
            self.stack.setCurrentWidget(self.video)
        elif kind == "image" and self.win.current:
            self.image.set_path(self.win.current.path)
            self.stack.setCurrentWidget(self.image)
        else:
            self.stack.setCurrentWidget(self.art)
        self.refresh(force=True)

    def refresh(self, force=False):
        w = self.win
        it = w.current
        self.title.setText(w.np_title.text() if it else "Nothing playing")
        if self.kind != "image":
            self.art.set_art(w.audio_view.art or (w.thumbs.get(it) if it else None))
        if w.engine and it and not w.qt_image:
            length, t = w.engine.length(), w.engine.time()
            self.sub.setText(f"{fmt_time(t)}  /  {fmt_time(length)}" if length else w.np_sub.text())
            if length and not self.seek.dragging:
                self.seek.blockSignals(True)
                self.seek.setValue(int(t * 10000 / length))
                self.seek.blockSignals(False)
            self.seek.setEnabled(True)
        else:
            self.sub.setText(w.np_sub.text())
            self.seek.setEnabled(False)
        playing = w.is_playing()
        if force or playing != self._last_playing:
            self._last_playing = playing
            self.b_play.setIcon(T.icon("pause" if playing else "play", T.WHITE, 15, T.WHITE))

    # ---------------------------------------------------------- window
    def place(self, saved_geometry):
        if saved_geometry and self.restoreGeometry(QByteArray.fromBase64(saved_geometry.encode())):
            return
        self.resize(400, 300)
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)

    def showEvent(self, e):
        super().showEvent(e)
        hwnd = wintypes.HWND(int(self.winId()))
        try:
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(ctypes.c_int(2)), 4)
            sand = QColor(T.SAND)
            colorref = sand.red() | (sand.green() << 8) | (sand.blue() << 16)
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(ctypes.c_uint(colorref)), 4)
        except Exception:
            pass
        self.set_on_top(self.b_pin.isChecked())
        self.timer.start()
        self.refresh(force=True)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def set_on_top(self, on):
        ctypes.windll.user32.SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(-1 if on else -2),
                                          0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    def closeEvent(self, e):
        e.ignore()
        self.win.exit_mini()

    def _edges(self, pos):
        r = self.rect()
        edges = Qt.Edges()
        if pos.x() <= EDGE:
            edges |= Qt.LeftEdge
        elif pos.x() >= r.width() - EDGE:
            edges |= Qt.RightEdge
        if pos.y() <= EDGE:
            edges |= Qt.TopEdge
        elif pos.y() >= r.height() - EDGE:
            edges |= Qt.BottomEdge
        return edges

    def _cursor_for(self, edges):
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        if edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            return Qt.SizeBDiagCursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return None

    # Presses on video, art, text or empty strip space bubble up here: drag to move, edges to resize.
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        pos = self.mapFromGlobal(e.globalPosition().toPoint())
        edges = self._edges(pos)
        handle = self.windowHandle()
        if edges:
            handle.startSystemResize(edges)
        else:
            handle.startSystemMove()
        e.accept()

    def mouseMoveEvent(self, e):
        cur = self._cursor_for(self._edges(self.mapFromGlobal(e.globalPosition().toPoint())))
        if cur is None:
            self.unsetCursor()
        else:
            self.setCursor(cur)

    def mouseDoubleClickEvent(self, e):
        self.win.exit_mini()

    def contextMenuEvent(self, e):
        self.win.more_menu.exec(e.globalPos())

    def wheelEvent(self, e):
        self.win.nudge_volume(5 if e.angleDelta().y() > 0 else -5)
