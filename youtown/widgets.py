from datetime import datetime

from PySide6.QtCore import (QAbstractListModel, QEasingCurve, QModelIndex, QPoint, QPropertyAnimation, QRect,
                            QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImageReader, QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QLabel, QListView, QMenu, QSlider, QStyle,
                               QStyledItemDelegate, QStyleOptionSlider, QWidget)

from . import theme as T

ItemRole = Qt.UserRole + 1
TYPE_LABEL = {"video": "Video", "audio": "Music", "image": "Image"}


def fmt_time(ms):
    if ms is None or ms < 0:
        return "0:00"
    s = int(ms // 1000)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_size(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{b:.0f} {unit}" if unit in ("B", "KB") else f"{b:.1f} {unit}"
        b /= 1024
    return ""


def fmt_date(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%b %d, %Y")
    except (OSError, ValueError, OverflowError):
        return ""


def menu(parent=None, title=""):
    m = QMenu(title, parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    return m


def submenu(parent_menu, title):
    m = menu(parent_menu, title)
    parent_menu.addMenu(m)
    return m


class ClickSlider(QSlider):
    """Slider that jumps to where you click, and reports drags."""

    moved = Signal(int)  # final value after click/drag

    def __init__(self, orient=Qt.Horizontal, parent=None):
        super().__init__(orient, parent)
        self.dragging = False
        self.setCursor(Qt.PointingHandCursor)
        self.sliderPressed.connect(lambda: setattr(self, "dragging", True))
        self.sliderReleased.connect(self._released)

    def _released(self):
        self.dragging = False
        self.moved.emit(self.value())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
            if not handle.contains(e.position().toPoint()):
                v = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(e.position().x()) - 6,
                                                   max(1, self.width() - 12))
                self.setValue(v)
                self.moved.emit(v)
        super().mousePressEvent(e)


class VideoSurface(QFrame):
    """Native child window that libVLC renders into."""

    doubleClicked = Signal()
    clicked = Signal()
    wheel = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoSurface")
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(T.INK))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def wheelEvent(self, e):
        self.wheel.emit(1 if e.angleDelta().y() > 0 else -1)


class ImageView(QWidget):
    """Fits an image (or animated GIF) into the view, centered, on ink."""

    doubleClicked = Signal()
    wheel = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageView")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pix = None
        self.movie = None
        self._scaled = None

    @staticmethod
    def can_read(path):
        r = QImageReader(path)
        return r.canRead()

    def set_path(self, path):
        self.clear()
        r = QImageReader(path)
        r.setAutoTransform(True)
        if r.supportsAnimation() and r.imageCount() > 1:
            self.movie = QMovie(path)
            self.movie.frameChanged.connect(self._frame)
            self.movie.start()
            return True
        img = r.read()
        if img.isNull():
            return False
        self.pix = QPixmap.fromImage(img)
        self._scaled = None
        self.update()
        return True

    def _frame(self):
        self.pix = self.movie.currentPixmap()
        self._scaled = None
        self.update()

    def clear(self):
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.pix = None
        self._scaled = None
        self.update()

    def resizeEvent(self, e):
        self._scaled = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.INK))
        if not self.pix:
            return
        dpr = self.devicePixelRatioF()
        if self._scaled is None:
            target = self.size() * dpr
            pm = self.pix
            if pm.width() > target.width() or pm.height() > target.height() or self.movie is None:
                pm = pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if pm.width() > target.width() or pm.height() > target.height():
                pm = pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            self._scaled = pm
        pm = self._scaled
        w, h = pm.width() / dpr, pm.height() / dpr
        p.drawPixmap(int((self.width() - w) / 2), int((self.height() - h) / 2), pm)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()

    def wheelEvent(self, e):
        self.wheel.emit(1 if e.angleDelta().y() > 0 else -1)


class AudioView(QWidget):
    """Now-playing card for music: artwork, title, artist on a soft nude gradient."""

    wheel = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.art = None
        self.title = ""
        self.artist = ""
        self.playing = False

    def set_info(self, title, artist, art=None):
        self.title, self.artist, self.art = title, artist, art
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(T.NUDE))
        g.setColorAt(1, QColor(T.CREAM))
        p.fillRect(self.rect(), g)
        side = int(min(self.width() * 0.5, self.height() * 0.48, 340))
        x = (self.width() - side) // 2
        y = max(24, (self.height() - side - 110) // 2)
        r = QRectF(x, y, side, side)
        # soft shadow
        for i in range(10, 0, -1):
            sh = QPainterPath()
            sh.addRoundedRect(r.adjusted(-i, -i + 10, i, i + 10), 28 + i, 28 + i)
            p.fillPath(sh, QColor(176, 138, 138, 5))
        path = QPainterPath()
        path.addRoundedRect(r, 26, 26)
        p.save()
        p.setClipPath(path)
        if self.art and not self.art.isNull():
            pm = self.art.scaled(side * 2, side * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            src = QRect((pm.width() - side * 2) // 2, (pm.height() - side * 2) // 2, side * 2, side * 2)
            p.drawPixmap(r, pm, QRectF(src))
        else:
            gg = QLinearGradient(r.topLeft(), r.bottomRight())
            gg.setColorAt(0, QColor(T.BUTTER))
            gg.setColorAt(1, QColor(T.MAUVE))
            p.fillRect(r, gg)
            ic = T.pixmap("audio", T.WHITE, max(24, side // 4))
            p.drawPixmap(int(r.center().x() - ic.width() / ic.devicePixelRatio() / 2),
                         int(r.center().y() - ic.height() / ic.devicePixelRatio() / 2), ic)
        p.restore()
        ty = int(r.bottom()) + 30
        f = QFont(T.SERIF, 20)
        p.setFont(f)
        p.setPen(QColor(T.INK))
        fm = QFontMetrics(f)
        p.drawText(QRect(20, ty, self.width() - 40, fm.height() + 6), Qt.AlignHCenter,
                   fm.elidedText(self.title, Qt.ElideRight, self.width() - 60))
        f2 = QFont(T.SANS, 10)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f2)
        p.setPen(QColor(T.GOLD))
        p.drawText(QRect(20, ty + fm.height() + 10, self.width() - 40, 24), Qt.AlignHCenter,
                   (self.artist or "").upper())

    def wheelEvent(self, e):
        self.wheel.emit(1 if e.angleDelta().y() > 0 else -1)


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer(self, singleShot=True, timeout=self._fade_out)
        self.hide()

    def show_msg(self, text, ms=2400):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 130)
        self.raise_()
        self.show()
        self.anim.stop()
        self.anim.setStartValue(self.fx.opacity() if self.isVisible() else 0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
        QTimer.singleShot(200, lambda: self.fx.opacity() < 0.05 and self.hide())


# ---------------- library ----------------
class LibraryModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.rows = {}

    def set_items(self, items):
        self.beginResetModel()
        self.items = items
        self.rows = {it.path: i for i, it in enumerate(items)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        it = self.items[index.row()]
        if role == ItemRole:
            return it
        if role == Qt.ToolTipRole:
            return it.path
        if role == Qt.DisplayRole:
            return it.name
        return None

    def refresh_path(self, path):
        r = self.rows.get(path)
        if r is not None:
            idx = self.index(r)
            self.dataChanged.emit(idx, idx, [ItemRole])


class LibraryDelegate(QStyledItemDelegate):
    def __init__(self, view, thumbs, current_path):
        super().__init__(view)
        self.view = view
        self.thumbs = thumbs
        self.current_path = current_path  # callable
        self.f_name = QFont(T.SANS, 10)
        self.f_name.setWeight(QFont.DemiBold)
        self.f_meta = QFont(T.SANS, 8)
        self.f_badge = QFont(T.SANS, 7)
        self.f_badge.setWeight(QFont.Bold)
        self.f_badge.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)

    def sizeHint(self, option, index):
        if self.view.viewMode() == QListView.IconMode:
            return self.view.gridSize()
        return QSize(max(200, self.view.viewport().width() - 4), 64)

    def _draw_thumb(self, p, rect, it, radius):
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, QColor(T.TYPE_BG.get(it.type, T.CREAM)))
        pm = self.thumbs.get(it)
        if pm is not None:
            dpr = pm.devicePixelRatio() or 1
            pw, ph = pm.width() / dpr, pm.height() / dpr
            scale = max(rect.width() / pw, rect.height() / ph)
            sw, sh = rect.width() / scale, rect.height() / scale
            src = QRectF((pw - sw) / 2 * dpr, (ph - sh) / 2 * dpr, sw * dpr, sh * dpr)
            p.drawPixmap(QRectF(rect), pm, src)
        else:
            s = max(16, min(36, rect.height() // 3))
            ic = T.pixmap(it.type if it.type in ("video", "audio", "image") else "video", T.TAUPE, s)
            p.drawPixmap(rect.center().x() - s // 2, rect.center().y() - s // 2, ic)
        p.restore()

    def paint(self, p, option, index):
        it = index.data(ItemRole)
        if it is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hovered = bool(option.state & QStyle.State_MouseOver)
        playing = self.current_path() == it.path
        if self.view.viewMode() == QListView.IconMode:
            self._paint_grid(p, option.rect, it, hovered, playing)
        else:
            self._paint_list(p, option.rect, it, hovered, playing)
        p.restore()

    def _paint_grid(self, p, cell, it, hovered, playing):
        r = cell.adjusted(9, 9, -9, -9)
        th = int(r.width() * 10 / 16)
        trect = QRect(r.left(), r.top(), r.width(), th)
        self._draw_thumb(p, trect, it, 16)
        if playing or hovered:
            pen = QPen(QColor(T.GOLD if playing else T.MAUVE), 2 if playing else 1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(trect).adjusted(1, 1, -1, -1), 15, 15)
        # extension badge
        if it.ext:
            p.setFont(self.f_badge)
            fm = QFontMetrics(self.f_badge)
            txt = it.ext.upper()
            bw = fm.horizontalAdvance(txt) + 14
            br = QRectF(trect.left() + 9, trect.top() + 9, bw, 19)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 225))
            p.drawRoundedRect(br, 9.5, 9.5)
            p.setPen(QColor(T.GRAY))
            p.drawText(br, Qt.AlignCenter, txt)
        if playing:
            p.setFont(self.f_badge)
            br = QRectF(trect.left() + 9, trect.bottom() - 27, 70, 19)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.BUTTER))
            p.drawRoundedRect(br, 9.5, 9.5)
            p.setPen(QColor(T.GOLD))
            p.drawText(br, Qt.AlignCenter, "NOW PLAYING")
        elif hovered:
            c = QRectF(trect.right() - 42, trect.bottom() - 42, 32, 32)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.INK))
            p.drawEllipse(c)
            ic = T.pixmap("play", T.WHITE, 14)
            p.drawPixmap(int(c.center().x() - 6), int(c.center().y() - 7), ic)
        # text
        p.setFont(self.f_name)
        fm = QFontMetrics(self.f_name)
        p.setPen(QColor(T.GOLD if playing else T.INK))
        ny = trect.bottom() + 8
        p.drawText(QRect(r.left() + 2, ny, r.width() - 4, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(it.title, Qt.ElideRight, r.width() - 4))
        p.setFont(self.f_meta)
        fm2 = QFontMetrics(self.f_meta)
        p.setPen(QColor(T.MUTED))
        meta = f"{TYPE_LABEL.get(it.type, '')}  ·  {fmt_size(it.size)}  ·  {fmt_date(it.mtime)}" if not it.url else "Stream"
        p.drawText(QRect(r.left() + 2, ny + fm.height() + 2, r.width() - 4, fm2.height()), Qt.AlignLeft,
                   fm2.elidedText(meta, Qt.ElideRight, r.width() - 4))

    def _paint_list(self, p, cell, it, hovered, playing):
        r = cell.adjusted(8, 3, -12, -3)
        if playing or hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.NUDE if playing else T.CREAM))
            p.drawRoundedRect(QRectF(r), 12, 12)
        trect = QRect(r.left() + 8, r.top() + 6, 76, r.height() - 12)
        self._draw_thumb(p, trect, it, 9)
        x = trect.right() + 16
        meta_w = 250
        name_w = max(80, int((r.right() - x - meta_w) * 0.55))
        p.setFont(self.f_name)
        fm = QFontMetrics(self.f_name)
        p.setPen(QColor(T.GOLD if playing else T.INK))
        p.drawText(QRect(x, r.top(), name_w, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(it.title, Qt.ElideRight, name_w))
        p.setFont(self.f_meta)
        fm2 = QFontMetrics(self.f_meta)
        p.setPen(QColor(T.MUTED))
        dx = x + name_w + 16
        dw = r.right() - meta_w - dx
        if dw > 60:
            p.drawText(QRect(dx, r.top(), dw, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                       fm2.elidedText(it.dir, Qt.ElideMiddle, dw))
        meta = f"{it.ext.upper()}  ·  {fmt_size(it.size)}  ·  {fmt_date(it.mtime)}" if not it.url else "Stream"
        p.drawText(QRect(r.right() - meta_w, r.top(), meta_w - 12, r.height()), Qt.AlignVCenter | Qt.AlignRight, meta)


class LibraryView(QListView):
    activatedItem = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Library")
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setViewportMargins(14, 8, 6, 8)
        self.set_layout("grid")
        self.clicked.connect(lambda idx: self.activatedItem.emit(idx.row()))

    def set_layout(self, layout):
        if layout == "list":
            self.setViewMode(QListView.ListMode)
            self.setGridSize(QSize())
            self.setSpacing(0)
        else:
            self.setViewMode(QListView.IconMode)
            self.setWrapping(True)
            self.setFlow(QListView.LeftToRight)
            self.setSpacing(0)
            self._update_grid()
        self.doItemsLayout()

    def _update_grid(self):
        if self.viewMode() != QListView.IconMode:
            return
        w = self.viewport().width() - 24  # Qt keeps room for the scrollbar when wrapping
        cols = max(1, w // 205)
        cw = w // cols
        th = int((cw - 18) * 10 / 16)
        self.setGridSize(QSize(cw, th + 18 + 50))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.viewMode() == QListView.IconMode:
            self._update_grid()
        else:
            self.doItemsLayout()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._update_grid)
