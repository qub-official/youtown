import ctypes
import os
import random
import re
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QGuiApplication, QKeySequence, QPainter, QPainterPath, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QSystemTrayIcon,
                               QToolButton, QVBoxLayout, QWidget, QAbstractItemView)

from . import theme as T
from . import winintegration as W
from .config import APP_NAME, FROZEN, VERSION
from .engine import ASPECTS, SPEEDS, Engine, VLC_DIR
from .formats import OPENABLE, SUBTITLE, ext_of
from .library import Item, Scanner, items_from_paths, load_library
from .mini import MiniPlayer
from .preview import PreviewCard
from .playlists import Playlists
from .thumbs import ThumbProvider
from .widgets import (AudioView, ClickSlider, ImageView, LibraryDelegate, LibraryModel, LibraryView, Toast,
                      VideoSurface, fmt_time, menu, submenu)

VIEW_TITLE = {"all": "All media", "video": "Videos", "audio": "Music", "image": "Images", "recent": "Recently played"}
VIEW_EYEBROW = {"all": "YOUR LIBRARY", "video": "WATCH", "audio": "LISTEN", "image": "LOOK", "recent": "AGAIN",
                "folder": "FOLDER", "playlist": "PLAYLIST"}


def rounded(pm: QPixmap, size: int, radius: int) -> QPixmap:
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    out = QPixmap(int(size * dpr), int(size * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    if pm and not pm.isNull():
        s = pm.scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        s.setDevicePixelRatio(dpr)
        p.drawPixmap(int((size - s.width() / dpr) / 2), int((size - s.height() / dpr) / 2), s)
    p.end()
    return out


def tool(icon_name, tip, color=T.GRAY, size=20, active=T.INK, checkable=False, obj=None):
    b = QToolButton()
    b.setIcon(T.icon(icon_name, color, size, active))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(checkable)
    if obj:
        b.setObjectName(obj)
    return b


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(T.app_icon())
        self.resize(1300, 840)
        self.setMinimumSize(940, 600)
        self.setAcceptDrops(True)

        self.engine = None
        self.items, self.by_path, self.signature = [], {}, None
        self.view_name, self.folder, self.query = "all", None, ""
        self.queue, self.qi, self.history = [], -1, []
        self.current = None
        self.qt_image = False
        self.ab = [None, None]
        self.pending_resume = None
        self.pending_open = []
        self.vol_applied = False
        self.meta_done = False
        self.last_playing = None
        self.last_sec = -1
        self.play_started = 0.0
        self.error_handled = False
        self.speed = 1.0
        self.aspect = "Default"
        self.eq_index = -1
        self.scanner = None
        self.scanning = False
        self.quitting = False
        self.tray_hinted = False
        self.last_cursor = None
        self.last_move = time.monotonic()
        self.last_save = 0.0
        self.taskbar = None
        self.mini = None
        self.fail_count = 0
        self.stage_kind = "video"
        self.video_home = "stage"
        self.preview_dismissed = False
        self.thumb_icons = {}

        self.playlists = Playlists()
        self.playlist_buttons = {}
        self.thumbs = ThumbProvider()
        self.thumbs.ready.connect(self._thumb_ready)

        self._build()
        self._build_menus()
        self._shortcuts()
        self._tray()

        self.poll = QTimer(self, interval=120, timeout=self._poll)
        self.poll.start()
        self.slide_timer = QTimer(self, singleShot=True, timeout=lambda: self.next(auto=True))
        self.save_timer = QTimer(self, singleShot=True, interval=600, timeout=self.s.save)
        self.search_timer = QTimer(self, singleShot=True, interval=160, timeout=self._apply_search)

        if self.s.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(self.s["geometry"].encode()))

        lib = load_library()
        if lib is not None:
            self.set_library(lib)
        else:
            self.refresh()
        self._render_folders()
        self._render_playlists()
        QTimer.singleShot(400, self.scan)

    # ================================================================ UI
    def _build(self):
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = self._build_sidebar()
        h.addWidget(self.sidebar)

        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        middle = QHBoxLayout()
        middle.setSpacing(0)
        self.pages = QStackedWidget()
        self.page_library = self._build_library_page()
        self.page_player = self._build_player_page()
        self.page_settings = self._build_settings_page()
        for pg in (self.page_library, self.page_player, self.page_settings):
            self.pages.addWidget(pg)
        middle.addWidget(self.pages, 1)
        self.queue_panel = self._build_queue_panel()
        self.queue_panel.hide()
        middle.addWidget(self.queue_panel)
        v.addLayout(middle, 1)
        self.preview = PreviewCard(right, self.open_now_playing, self._dismiss_preview)
        self.pages.installEventFilter(self)
        self.bar = self._build_player_bar()
        v.addWidget(self.bar)
        h.addWidget(right, 1)
        self.toast = Toast(root)

    def _build_sidebar(self):
        sb = QFrame(objectName="Sidebar")
        sb.setFixedWidth(236)
        v = QVBoxLayout(sb)
        v.setContentsMargins(16, 22, 16, 14)
        v.setSpacing(2)
        brand = QHBoxLayout()
        brand.setSpacing(0)
        logo = QLabel()
        logo.setPixmap(QPixmap.fromImage(T.app_icon_image(64)).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)
        brand.addSpacing(10)
        brand.addWidget(QLabel("youtown", objectName="Brand"))
        brand.addWidget(QLabel(".", objectName="BrandDot"))
        brand.addStretch()
        v.addLayout(brand)
        v.addSpacing(2)
        tag = QLabel("films · music · moments", objectName="Tagline")
        tag.setContentsMargins(42, 0, 0, 0)
        v.addWidget(tag)
        v.addSpacing(22)

        self.nav = {}
        self.counts = {}
        for key, ic, label in (("all", "all", "All media"), ("video", "video", "Videos"), ("audio", "audio", "Music"),
                               ("image", "image", "Images"), ("recent", "recent", "Recently played")):
            b = self._nav_button(ic, label)
            b.clicked.connect(lambda _=False, k=key: self.set_view(k))
            if key != "recent":
                c = QLabel("", objectName="Count")
                c.setAttribute(Qt.WA_TransparentForMouseEvents)
                lay = QHBoxLayout(b)
                lay.setContentsMargins(0, 0, 12, 0)
                lay.addStretch()
                lay.addWidget(c)
                self.counts[key] = c
            self.nav[key] = b
            v.addWidget(b)
        self.nav["all"].setChecked(True)
        v.addSpacing(6)
        now = self._nav_button("screen", "Now playing")
        now.clicked.connect(self.open_now_playing)
        now.setToolTip("Back to what's playing (Ctrl+P)")
        self.now_dot = QLabel("", objectName="Count")
        self.now_dot.setStyleSheet(f"color: {T.GOLD}; font-size: 13px;")
        self.now_dot.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QHBoxLayout(now)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.addStretch()
        lay.addWidget(self.now_dot)
        now.hide()
        self.nav["now"] = now
        v.addWidget(now)

        v.addSpacing(14)
        lists = QWidget()
        lv = QVBoxLayout(lists)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(1)

        def section(title, tip):
            row = QHBoxLayout()
            lbl = QLabel(title, objectName="SectionLabel")
            lbl.setContentsMargins(12, 0, 0, 0)
            row.addWidget(lbl)
            row.addStretch()
            add = tool("plus", tip, T.TAUPE, 16)
            row.addWidget(add)
            lv.addLayout(row)
            lv.addSpacing(4)
            return add

        add_pl = section("PLAYLISTS", "New playlist")
        pl_menu = menu(self)
        pl_menu.addAction(T.icon("plus", T.GRAY, 16), "New playlist…", lambda: self.new_playlist())
        pl_menu.addAction(T.icon("open", T.GRAY, 16), "Import playlist file (.m3u, .pls, .xspf)…", self.import_playlist)
        add_pl.setMenu(pl_menu)
        add_pl.setPopupMode(QToolButton.InstantPopup)
        self.playlist_box = QWidget()
        self.playlist_layout = QVBoxLayout(self.playlist_box)
        self.playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.playlist_layout.setSpacing(1)
        lv.addWidget(self.playlist_box)
        lv.addSpacing(16)

        add = section("FOLDERS", "Add a folder to your library")
        add.clicked.connect(self.add_folder)
        self.folder_box = QWidget()
        self.folder_layout = QVBoxLayout(self.folder_box)
        self.folder_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_layout.setSpacing(1)
        lv.addWidget(self.folder_box)
        lv.addStretch()
        sc = QScrollArea()
        sc.setWidget(lists)
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet(f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {T.CREAM}; }}")
        v.addWidget(sc, 1)

        self.nav["settings"] = self._nav_button("settings", "Settings")
        self.nav["settings"].clicked.connect(lambda: self.set_view("settings"))
        v.addWidget(self.nav["settings"])
        return sb

    def _nav_button(self, ic, label):
        b = QPushButton("   " + label, objectName="Nav")
        b.setIcon(T.icon(ic, T.GRAY, 18))
        b.setIconSize(QSize(18, 18))
        b.setCheckable(True)
        b.setAutoExclusive(False)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(40)
        return b

    def _build_library_page(self):
        pg = QWidget(objectName="LibraryPage")
        v = QVBoxLayout(pg)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        hh = QHBoxLayout(head)
        hh.setContentsMargins(32, 26, 26, 16)
        hh.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.eyebrow = QLabel("YOUR LIBRARY", objectName="Eyebrow")
        self.title = QLabel("All media", objectName="PageTitle")
        self.subtitle = QLabel("", objectName="PageSub")
        titles.addWidget(self.eyebrow)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        self.pl_actions = QWidget()
        pa = QHBoxLayout(self.pl_actions)
        pa.setContentsMargins(0, 8, 0, 0)
        pa.setSpacing(8)
        b_play = QPushButton("  Play all", objectName="Primary")
        b_play.setIcon(T.icon("play", T.WHITE, 14))
        b_play.clicked.connect(lambda: self.model.items and self.play_list(self.model.items, 0))
        b_shuf = QPushButton("  Shuffle")
        b_shuf.setIcon(T.icon("shuffle", T.INK, 15))
        b_shuf.clicked.connect(self.shuffle_view)
        b_more = QToolButton(objectName="Pill")
        b_more.setText("···")
        b_more.setToolTip("Playlist options")
        b_more.setPopupMode(QToolButton.InstantPopup)
        pm = menu(self)
        pm.addAction("Rename…", lambda: self.rename_playlist(self.folder))
        pm.addAction("Export as .m3u…", lambda: self.export_playlist(self.folder))
        pm.addSeparator()
        pm.addAction(T.icon("trash", T.GRAY, 16), "Delete playlist", lambda: self.delete_playlist(self.folder))
        b_more.setMenu(pm)
        for b in (b_play, b_shuf, b_more):
            b.setCursor(Qt.PointingHandCursor)
            pa.addWidget(b)
        pa.addStretch()
        self.pl_actions.hide()
        titles.addWidget(self.pl_actions)
        hh.addLayout(titles)
        hh.addStretch()

        self.search = QLineEdit(objectName="Search")
        self.search.setPlaceholderText("Search your media…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(T.icon("search", T.TAUPE, 16), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        hh.addWidget(self.search, 0, Qt.AlignBottom)

        self.sort = QComboBox()
        for key, label in (("name", "Name"), ("newest", "Newest"), ("oldest", "Oldest"), ("largest", "Largest"),
                           ("type", "Type")):
            self.sort.addItem(label, key)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.s["sort"])))
        self.sort.currentIndexChanged.connect(self._sort_changed)
        self.sort.setCursor(Qt.PointingHandCursor)
        hh.addWidget(self.sort, 0, Qt.AlignBottom)

        seg = QFrame(objectName="SegBox")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.btn_grid = tool("grid", "Grid view", T.GRAY, 17, checkable=True, obj="Seg")
        self.btn_list = tool("list", "List view", T.GRAY, 17, checkable=True, obj="Seg")
        self.btn_grid.clicked.connect(lambda: self.set_layout("grid"))
        self.btn_list.clicked.connect(lambda: self.set_layout("list"))
        sl.addWidget(self.btn_grid)
        sl.addWidget(self.btn_list)
        hh.addWidget(seg, 0, Qt.AlignBottom)

        self.btn_open = tool("open", "Open…", T.GRAY, 20)
        self.btn_open.setPopupMode(QToolButton.InstantPopup)
        hh.addWidget(self.btn_open, 0, Qt.AlignBottom)
        rescan = tool("refresh", "Rescan library", T.GRAY, 20)
        rescan.clicked.connect(self.scan)
        hh.addWidget(rescan, 0, Qt.AlignBottom)
        v.addWidget(head)

        self.scanbar = QFrame(objectName="ScanBar")
        sbl = QHBoxLayout(self.scanbar)
        sbl.setContentsMargins(32, 6, 26, 6)
        self.scan_text = QLabel("", objectName="ScanText")
        self.scan_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        sbl.addWidget(self.scan_text)
        self.scanbar.hide()
        v.addWidget(self.scanbar)

        self.lib_stack = QStackedWidget()
        self.model = LibraryModel(self)
        self.view = LibraryView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(LibraryDelegate(self.view, self.thumbs, lambda: self.current.path if self.current else None))
        self.view.activatedItem.connect(lambda row: self.play_list(self.model.items, row))
        self.view.customContextMenuRequested.connect(self._item_menu)
        self.lib_stack.addWidget(self.view)

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch()
        circle = QLabel()
        circle.setFixedSize(84, 84)
        circle.setAlignment(Qt.AlignCenter)
        circle.setStyleSheet(f"background: {T.NUDE}; border-radius: 42px;")
        circle.setPixmap(T.pixmap("heart", T.MAUVE, 34))
        ev.addWidget(circle, 0, Qt.AlignHCenter)
        ev.addSpacing(16)
        self.empty_title = QLabel("Nothing here yet", objectName="EmptyTitle")
        self.empty_text = QLabel("", objectName="Hint")
        self.empty_text.setAlignment(Qt.AlignCenter)
        ev.addWidget(self.empty_title, 0, Qt.AlignHCenter)
        ev.addWidget(self.empty_text, 0, Qt.AlignHCenter)
        ev.addSpacing(16)
        btns = QHBoxLayout()
        btns.addStretch()
        b1 = QPushButton("Add a folder", objectName="Primary")
        b1.clicked.connect(self.add_folder)
        b2 = QPushButton("Open files")
        b2.clicked.connect(self.open_files)
        for b in (b1, b2):
            b.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b)
        btns.addStretch()
        ev.addLayout(btns)
        ev.addStretch()
        self.lib_stack.addWidget(empty)
        v.addWidget(self.lib_stack, 1)
        self.set_layout(self.s["layout"], save=False)
        return pg

    def _build_player_page(self):
        pg = QWidget()
        pg.setStyleSheet(f"background: {T.INK};")
        v = QVBoxLayout(pg)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.player_top = QFrame(objectName="PlayerTop")
        th = QHBoxLayout(self.player_top)
        th.setContentsMargins(12, 8, 12, 8)
        back = tool("back", "Back to library (Esc)", T.CREAM, 20, T.WHITE)
        back.clicked.connect(lambda: self.show_page("library"))
        th.addWidget(back)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        self.stage_title = QLabel("")
        self.stage_title.setStyleSheet(f"color: {T.CREAM}; font-family: '{T.SERIF}'; font-size: 15px;")
        self.stage_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.stage_path = QPushButton("")
        self.stage_path.setCursor(Qt.PointingHandCursor)
        self.stage_path.setToolTip("Show in File Explorer")
        self.stage_path.setIcon(T.icon("folder", T.TAUPE, 13))
        self.stage_path.setStyleSheet(f"QPushButton {{ background: transparent; border: none; padding: 0; color: {T.TAUPE};"
                                      f" font-size: 11px; text-align: left; }}"
                                      f" QPushButton:hover {{ color: {T.BUTTER}; text-decoration: underline; }}")
        self.stage_path.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.stage_path.clicked.connect(self.reveal_current)
        tcol.addWidget(self.stage_title)
        tcol.addWidget(self.stage_path)
        th.addLayout(tcol, 1)
        snap = tool("camera", "Take snapshot (Shift+S)", T.CREAM, 19, T.WHITE)
        snap.clicked.connect(self.snapshot)
        th.addWidget(snap)
        self.top_more = tool("more", "More", T.CREAM, 20, T.WHITE)
        self.top_more.setPopupMode(QToolButton.InstantPopup)
        th.addWidget(self.top_more)
        mini = tool("mini", "Mini player (Ctrl+M)", T.CREAM, 19, T.WHITE)
        mini.clicked.connect(self.enter_mini)
        th.addWidget(mini)
        fs = tool("full", "Fullscreen (F)", T.CREAM, 19, T.WHITE)
        fs.clicked.connect(self.toggle_fullscreen)
        th.addWidget(fs)
        v.addWidget(self.player_top)

        self.stage = QStackedWidget()
        self.video = VideoSurface()
        self.image_view = ImageView()
        self.audio_view = AudioView()
        for w in (self.video, self.image_view, self.audio_view):
            self.stage.addWidget(w)
            w.customContextMenuRequested.connect(lambda _p: self.more_menu.exec(QCursor.pos()))
            w.wheel.connect(self._wheel)
        self.video.doubleClicked.connect(self._video_double_clicked)
        self.video.clicked.connect(self._video_clicked)
        self.image_view.doubleClicked.connect(self.toggle_fullscreen)
        v.addWidget(self.stage, 1)
        return pg

    def _card(self, title, hint=None):
        card = QFrame(objectName="Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 20, 24, 22)
        v.setSpacing(10)
        v.addWidget(QLabel(title, objectName="CardTitle"))
        if hint:
            h = QLabel(hint, objectName="Hint")
            h.setWordWrap(True)
            v.addWidget(h)
        return card, v

    def _build_settings_page(self):
        pg = QScrollArea(objectName="SettingsPage")
        pg.setWidgetResizable(True)
        pg.setFrameShape(QFrame.NoFrame)
        inner = QWidget(objectName="SettingsInner")
        pg.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(32, 26, 32, 32)
        v.setSpacing(16)
        v.addWidget(QLabel("PREFERENCES", objectName="Eyebrow"))
        v.addWidget(QLabel("Settings", objectName="PageTitle"))
        v.addSpacing(4)

        card, cv = self._card("Library folders", "YouTown looks in these folders and all their subfolders.")
        self.settings_folders = QVBoxLayout()
        self.settings_folders.setSpacing(6)
        cv.addLayout(self.settings_folders)
        b = QPushButton("Add folder")
        b.setIcon(T.icon("plus", T.INK, 16))
        b.clicked.connect(self.add_folder)
        cv.addWidget(b, 0, Qt.AlignLeft)
        v.addWidget(card)

        card, cv = self._card("Default app", "Open your videos, music and images with YouTown when you double-click "
                                             "them in File Explorer. Windows asks you to confirm the choice in "
                                             "Settings → Default apps.")
        self.default_status = QLabel("", objectName="Status")
        self.default_status.setWordWrap(True)
        cv.addWidget(self.default_status)
        row = QHBoxLayout()
        b1 = QPushButton("Set as default app…", objectName="Primary")
        b1.clicked.connect(self.set_default)
        b2 = QPushButton("Remove registration", objectName="Ghost")
        b2.clicked.connect(self.remove_default)
        for b in (b1, b2):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch()
        cv.addLayout(row)
        v.addWidget(card)

        card, cv = self._card("Playback")
        for key, text in (("close_to_tray", "Keep playing in the tray when I close the window"),
                          ("media_keys", "Use keyboard media keys (play/pause, next, previous) while minimized"),
                          ("resume", "Continue videos where I left off")):
            c = QCheckBox(text)
            c.setChecked(bool(self.s[key]))
            c.toggled.connect(lambda on, k=key: self._set_setting(k, on))
            cv.addWidget(c)
        row = QHBoxLayout()
        row.addWidget(QLabel("Slideshow speed for images"))
        sp = QComboBox()
        for sec in (3, 5, 8, 15):
            sp.addItem(f"{sec} seconds", sec)
        sp.setCurrentIndex(max(0, sp.findData(self.s["slide_interval"])))
        sp.currentIndexChanged.connect(lambda _i: self._set_setting("slide_interval", sp.currentData()))
        row.addWidget(sp)
        row.addStretch()
        cv.addLayout(row)
        v.addWidget(card)

        card, cv = self._card("Keyboard shortcuts", "The same keys VLC uses.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        keys = [("Space", "Play / pause"), ("S", "Stop"), ("N / P", "Next / previous"), ("F · Esc", "Fullscreen / leave"),
                ("← →", "Jump 10 s (Shift 3 s, Ctrl 1 min)"), ("↑ ↓", "Volume"), ("M", "Mute"),
                ("[  ]  =", "Slower / faster / normal speed"), ("E", "Next frame"), ("T", "Show time"),
                ("B · V", "Cycle audio / subtitle track"), ("A", "Cycle aspect ratio"), ("G · H", "Subtitle delay"),
                ("J · K", "Audio delay"), ("L · R", "Loop / shuffle"), ("Shift+S", "Snapshot"), ("Ctrl+T", "Jump to time"),
                ("Ctrl+O", "Open files"), ("Ctrl+Shift+O", "Open folder"), ("Ctrl+N", "Open network stream"),
                ("Ctrl+L", "Show queue"), ("Ctrl+F", "Search")]
        for i, (k, d) in enumerate(keys):
            r, c = divmod(i, 2)
            kl = QLabel(k, objectName="Kbd")
            grid.addWidget(kl, r, c * 2, Qt.AlignRight)
            grid.addWidget(QLabel(d, objectName="Hint"), r, c * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        cv.addLayout(grid)
        v.addWidget(card)

        self.about = QLabel("", objectName="Hint")
        v.addWidget(self.about)
        v.addStretch()
        return pg

    def _build_queue_panel(self):
        panel = QFrame(objectName="QueuePanel")
        panel.setFixedWidth(300)
        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 20, 12, 12)
        head = QHBoxLayout()
        t = QVBoxLayout()
        t.setSpacing(0)
        t.addWidget(QLabel("QUEUE", objectName="Eyebrow"))
        t.addWidget(QLabel("Up next", objectName="CardTitle"))
        head.addLayout(t)
        head.addStretch()
        clear = QPushButton("Clear", objectName="Ghost")
        clear.clicked.connect(self.clear_queue)
        save_q = QPushButton("Save", objectName="Ghost")
        save_q.setToolTip("Save the queue as a playlist")
        save_q.clicked.connect(lambda: self.new_playlist([it.path for it in self.queue]))
        head.addWidget(save_q)
        head.addWidget(clear)
        close = tool("x", "Close", T.MUTED, 16)
        close.clicked.connect(lambda: self.toggle_queue(False))
        head.addWidget(close)
        v.addLayout(head)
        self.queue_list = QListWidget(objectName="Queue")
        self.queue_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.itemDoubleClicked.connect(lambda it: self._play_queue_row(self.queue_list.row(it)))
        self.queue_list.model().rowsMoved.connect(self._queue_reordered)
        self.queue_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self._queue_menu)
        v.addWidget(self.queue_list, 1)
        hint = QLabel("Double-click to play · drag to reorder", objectName="Hint")
        hint.setStyleSheet("font-size: 11px;")
        v.addWidget(hint)
        return panel

    def _build_player_bar(self):
        bar = QFrame(objectName="PlayerBar")
        bar.setFixedHeight(112)
        g = QGridLayout(bar)
        g.setContentsMargins(18, 12, 18, 14)
        g.setHorizontalSpacing(20)

        left = QHBoxLayout()
        left.setSpacing(12)
        self.np_art = QLabel()
        self.np_art.setCursor(Qt.PointingHandCursor)
        self.np_art.setToolTip("Show what's playing")
        self.np_art.mousePressEvent = lambda e: self.open_now_playing()
        self.np_art.setFixedSize(54, 54)
        self.np_art.setStyleSheet(f"background: {T.NUDE}; border-radius: 12px;")
        self.np_art.setAlignment(Qt.AlignCenter)
        self.np_art.setPixmap(T.pixmap("heart", T.MAUVE, 22))
        left.addWidget(self.np_art)
        tv = QVBoxLayout()
        tv.setSpacing(1)
        tv.addStretch()
        self.np_title = QLabel("Nothing playing", objectName="NowTitle")
        self.np_title.setCursor(Qt.PointingHandCursor)
        self.np_title.mousePressEvent = lambda e: self.open_now_playing()
        self.np_sub = QLabel("Pick something from your library", objectName="NowSub")
        self.np_sub.setCursor(Qt.PointingHandCursor)
        self.np_sub.mousePressEvent = lambda e: self.reveal_current()
        for l in (self.np_title, self.np_sub):
            l.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        tv.addWidget(self.np_title)
        tv.addWidget(self.np_sub)
        tv.addStretch()
        left.addLayout(tv, 1)
        lw = QWidget()
        lw.setLayout(left)
        g.addWidget(lw, 0, 0)

        center = QVBoxLayout()
        center.setSpacing(14)
        btns = QHBoxLayout()
        btns.setSpacing(6)
        btns.addStretch()
        self.btn_shuffle = tool("shuffle", "Shuffle (R)", T.MUTED, 18, T.INK, checkable=True)
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        self.btn_stop = tool("stop", "Stop (S)", T.GRAY, 16)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_prev = tool("prev", "Previous (P)", T.INK, 20)
        self.btn_prev.clicked.connect(self.prev)
        self.btn_play = tool("play", "Play (Space)", T.WHITE, 20, T.WHITE, obj="Play")
        self.btn_play.setFixedSize(46, 46)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next = tool("next", "Next (N)", T.INK, 20)
        self.btn_next.clicked.connect(self.next)
        self.btn_repeat = tool("repeat", "Repeat (L)", T.MUTED, 18, T.INK)
        self.btn_repeat.clicked.connect(self.cycle_repeat)
        for b in (self.btn_shuffle, self.btn_stop, self.btn_prev, self.btn_play, self.btn_next, self.btn_repeat):
            btns.addWidget(b)
        btns.addStretch()
        center.addLayout(btns)
        seek = QHBoxLayout()
        seek.setSpacing(10)
        self.t_cur = QLabel("0:00", objectName="Time")
        self.t_dur = QLabel("0:00", objectName="Time")
        for l in (self.t_cur, self.t_dur):
            l.setFixedWidth(52)
            l.setAlignment(Qt.AlignCenter)
        self.seek = ClickSlider()
        self.seek.setRange(0, 10000)
        self.seek.moved.connect(self._seek_to)
        self.seek.valueChanged.connect(self._seek_preview)
        seek.addWidget(self.t_cur)
        seek.addWidget(self.seek, 1)
        seek.addWidget(self.t_dur)
        center.addLayout(seek)
        cw = QWidget()
        cw.setLayout(center)
        g.addWidget(cw, 0, 1)

        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch()
        self.btn_speed = QToolButton(objectName="Pill")
        self.btn_speed.setText("1×")
        self.btn_speed.setToolTip("Playback speed  ( [  ]  = )")
        self.btn_speed.setPopupMode(QToolButton.InstantPopup)
        self.btn_speed.setCursor(Qt.PointingHandCursor)
        right.addWidget(self.btn_speed)
        right.addSpacing(4)
        self.btn_queue = tool("queue", "Queue (Ctrl+L)", T.GRAY, 19, T.INK, checkable=True)
        self.btn_queue.clicked.connect(lambda on: self.toggle_queue(on))
        right.addWidget(self.btn_queue)
        self.btn_mini = tool("mini", "Mini player (Ctrl+M)", T.GRAY, 19, T.INK)
        self.btn_mini.clicked.connect(self.enter_mini)
        right.addWidget(self.btn_mini)
        self.btn_stage = tool("screen", "Show / hide what's playing (Ctrl+P)", T.GRAY, 19, T.INK)
        self.btn_stage.clicked.connect(self._toggle_stage)
        right.addWidget(self.btn_stage)
        self.btn_mute = tool("vol", "Mute (M)", T.GRAY, 19, T.INK)
        self.btn_mute.clicked.connect(self.toggle_mute)
        right.addWidget(self.btn_mute)
        self.volume = ClickSlider()
        self.volume.setObjectName("Volume")
        self.volume.setRange(0, 125)
        self.volume.setFixedWidth(104)
        self.volume.setValue(int(self.s["volume"]))
        self.volume.valueChanged.connect(self._volume_changed)
        self.volume.setToolTip("Volume")
        right.addWidget(self.volume)
        right.addSpacing(4)
        self.btn_full = tool("full", "Fullscreen (F)", T.GRAY, 18, T.INK)
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        right.addWidget(self.btn_full)
        self.bar_more = tool("more", "More", T.GRAY, 20, T.INK)
        self.bar_more.setPopupMode(QToolButton.InstantPopup)
        right.addWidget(self.bar_more)
        rw = QWidget()
        rw.setLayout(right)
        g.addWidget(rw, 0, 2)
        g.setColumnStretch(0, 10)
        g.setColumnStretch(1, 14)
        g.setColumnStretch(2, 10)
        self._render_modes()
        self._render_volume()
        return bar

    # ------------------------------------------------------------ menus
    def _build_menus(self):
        om = menu(self)
        om.addAction(T.icon("open", T.GRAY, 16), "Open files…", self.open_files, QKeySequence("Ctrl+O"))
        om.addAction(T.icon("folder", T.GRAY, 16), "Open folder…", self.open_folder, QKeySequence("Ctrl+Shift+O"))
        om.addAction(T.icon("link", T.GRAY, 16), "Open network stream…", self.open_url, QKeySequence("Ctrl+N"))
        om.addSeparator()
        om.addAction(T.icon("plus", T.GRAY, 16), "Add folder to library…", self.add_folder)
        self.btn_open.setMenu(om)

        self.speed_menu = menu(self, "Speed")
        self.speed_group = QActionGroup(self)
        for sp in SPEEDS:
            a = self.speed_menu.addAction(f"{sp:g}×" + ("  (normal)" if sp == 1 else ""))
            a.setCheckable(True)
            a.setData(sp)
            a.setChecked(sp == 1.0)
            self.speed_group.addAction(a)
            a.triggered.connect(lambda _=False, v=sp: self.set_speed(v))
        self.btn_speed.setMenu(self.speed_menu)

        m = menu(self)
        pb = submenu(m, "Playback")
        pb.addMenu(self.speed_menu)
        pb.addAction("Jump to time…", self.jump_to_time, QKeySequence("Ctrl+T"))
        self.act_ab = pb.addAction("A→B loop: set start", self.ab_loop)
        pb.addAction("Next frame", self.frame_step, QKeySequence("E"))
        pb.addSeparator()
        pb.addAction("Stop", self.stop, QKeySequence("S"))

        self.audio_menu = submenu(m, "Audio")
        self.audio_menu.aboutToShow.connect(self._fill_audio_menu)
        self.video_menu = submenu(m, "Video")
        self.video_menu.aboutToShow.connect(self._fill_video_menu)
        self.sub_menu = submenu(m, "Subtitles")
        self.sub_menu.aboutToShow.connect(self._fill_sub_menu)
        m.addSeparator()
        m.addAction(T.icon("mini", T.GRAY, 16), "Mini player", self.enter_mini, QKeySequence("Ctrl+M"))
        self.act_top = m.addAction("Always on top")
        self.act_top.setCheckable(True)
        self.act_top.toggled.connect(self.set_on_top)
        m.addAction("Show in File Explorer", self.reveal_current)
        m.addAction("File properties", lambda: self.current and not self.current.url and W.show_properties(self.current.path))
        self.more_pl_menu = submenu(m, "Add to playlist")
        self.more_pl_menu.aboutToShow.connect(self._fill_more_playlist_menu)
        self.more_menu = m
        self.bar_more.setMenu(m)
        self.top_more.setMenu(m)

    def _fill_more_playlist_menu(self):
        mm = self.more_pl_menu
        mm.clear()
        paths = [self.current.path] if self.current else []
        mm.addAction(T.icon("plus", T.GRAY, 16), "New playlist…", lambda: self.new_playlist(paths))
        for pl in self.playlists.items:
            mm.addAction(pl["name"], lambda _=False, pid=pl["id"]: self.add_to_playlist(pid, paths))
        mm.setEnabled(bool(paths))

    def _fill_audio_menu(self):
        mm = self.audio_menu
        mm.clear()
        tracks = submenu(mm, "Audio track")
        grp = QActionGroup(tracks)
        if self.engine:
            cur = self.engine.audio_track()
            for tid, name in self.engine.audio_tracks():
                a = tracks.addAction(name)
                a.setCheckable(True)
                a.setChecked(tid == cur)
                grp.addAction(a)
                a.triggered.connect(lambda _=False, t=tid: self.engine.set_audio_track(t))
        if tracks.isEmpty():
            tracks.addAction("No audio tracks").setEnabled(False)
        eq = submenu(mm, "Equalizer")
        g2 = QActionGroup(eq)
        presets = self.engine.eq_presets() if self.engine else []
        for i, name in [(-1, "Off")] + list(enumerate(presets)):
            a = eq.addAction(name)
            a.setCheckable(True)
            a.setChecked(i == self.eq_index)
            g2.addAction(a)
            a.triggered.connect(lambda _=False, k=i: self.set_eq(k))
        mm.addSeparator()
        mm.addAction("Audio delay −50 ms", lambda: self.nudge_delay("audio", -50), QKeySequence("J"))
        mm.addAction("Audio delay +50 ms", lambda: self.nudge_delay("audio", 50), QKeySequence("K"))
        mm.addAction("Reset audio delay", lambda: self.nudge_delay("audio", None))
        mm.addSeparator()
        mm.addAction("Mute", self.toggle_mute, QKeySequence("M"))

    def _fill_video_menu(self):
        mm = self.video_menu
        mm.clear()
        asp = submenu(mm, "Aspect ratio")
        grp = QActionGroup(asp)
        for a_ in ASPECTS:
            a = asp.addAction(a_)
            a.setCheckable(True)
            a.setChecked(a_ == self.aspect)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, v=a_: self.set_aspect(v))
        mm.addAction("Fullscreen", self.toggle_fullscreen, QKeySequence("F"))
        mm.addAction("Take snapshot", self.snapshot, QKeySequence("Shift+S"))

    def _fill_sub_menu(self):
        mm = self.sub_menu
        mm.clear()
        mm.addAction("Add subtitle file…", self.add_subtitle_file)
        tracks = submenu(mm, "Subtitle track")
        grp = QActionGroup(tracks)
        if self.engine:
            cur = self.engine.sub_track()
            for tid, name in self.engine.sub_tracks():
                a = tracks.addAction(name)
                a.setCheckable(True)
                a.setChecked(tid == cur)
                grp.addAction(a)
                a.triggered.connect(lambda _=False, t=tid: self.engine.set_sub_track(t))
        if tracks.isEmpty():
            tracks.addAction("No subtitles").setEnabled(False)
        mm.addSeparator()
        mm.addAction("Subtitle delay −50 ms", lambda: self.nudge_delay("sub", -50), QKeySequence("G"))
        mm.addAction("Subtitle delay +50 ms", lambda: self.nudge_delay("sub", 50), QKeySequence("H"))
        mm.addAction("Reset subtitle delay", lambda: self.nudge_delay("sub", None))

    def _shortcuts(self):
        keys = {
            "Space": self.toggle_play, "S": self.stop, "N": self.next, "P": self.prev, "F": self.toggle_fullscreen,
            "F11": self.toggle_fullscreen, "Escape": self.escape, "M": self.toggle_mute,
            "Up": lambda: self.nudge_volume(5), "Down": lambda: self.nudge_volume(-5),
            "Ctrl+Up": lambda: self.nudge_volume(5), "Ctrl+Down": lambda: self.nudge_volume(-5),
            "Right": lambda: self.jump(10_000), "Left": lambda: self.jump(-10_000),
            "Shift+Right": lambda: self.jump(3_000), "Shift+Left": lambda: self.jump(-3_000),
            "Ctrl+Right": lambda: self.jump(60_000), "Ctrl+Left": lambda: self.jump(-60_000),
            "]": lambda: self.step_speed(1), "[": lambda: self.step_speed(-1), "=": lambda: self.set_speed(1.0),
            "E": self.frame_step, "T": self.show_time, "V": lambda: self.cycle_track("sub"),
            "B": lambda: self.cycle_track("audio"), "A": self.cycle_aspect, "Shift+S": self.snapshot,
            "Ctrl+T": self.jump_to_time, "G": lambda: self.nudge_delay("sub", -50), "H": lambda: self.nudge_delay("sub", 50),
            "J": lambda: self.nudge_delay("audio", -50), "K": lambda: self.nudge_delay("audio", 50),
            "L": self.cycle_repeat, "R": self.toggle_shuffle, "Ctrl+L": lambda: self.toggle_queue(),
            "Ctrl+O": self.open_files, "Ctrl+Shift+O": self.open_folder, "Ctrl+N": self.open_url,
            "Ctrl+F": self.focus_search, "Ctrl+Q": self.quit_app, "Ctrl+M": self.enter_mini, "Ctrl+P": self.open_now_playing,
        }
        for k, fn in keys.items():
            QShortcut(QKeySequence(k), self, activated=fn, context=Qt.WindowShortcut)

    def _tray(self):
        self.tray = QSystemTrayIcon(T.app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        tm = menu(self)
        self.tray_title = tm.addAction("Nothing playing")
        self.tray_title.setEnabled(False)
        tm.addSeparator()
        self.tray_play = tm.addAction("Play", self.toggle_play)
        tm.addAction("Next", self.next)
        tm.addAction("Previous", self.prev)
        tm.addSeparator()
        tm.addAction(f"Show {APP_NAME}", self.bring_to_front)
        tm.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(tm)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and self.bring_to_front())
        self.tray.show()

    # ================================================================ engine / startup
    def showEvent(self, e):
        super().showEvent(e)
        if self.engine is None and not hasattr(self, "_engine_tried"):
            self._engine_tried = True
            QTimer.singleShot(0, self._init_engine)

    def _init_engine(self):
        try:
            self.engine = Engine(int(self.video.winId()))
        except Exception as ex:
            self.engine = None
            QMessageBox.warning(self, APP_NAME, f"The playback engine could not start.\n\n{ex}\n\n"
                                                "Install VLC 64-bit from videolan.org, then reopen YouTown.")
        self.about.setText(f"{APP_NAME} {VERSION}  ·  playback by libVLC "
                           f"{self.engine.version if self.engine else '(missing)'}  ·  made with ♡")
        hwnd = int(self.winId())
        if self.s["media_keys"]:
            W.register_media_keys(hwnd)
        self.taskbar = W.Taskbar(hwnd)
        QTimer.singleShot(800, self._setup_thumbbar)
        # The installed app registers itself so it appears in "Open with" and Default apps.
        if FROZEN and not os.environ.get("YOUTOWN_NO_REGISTER") and W.default_status() != "registered":
            try:
                W.register_default()
            except OSError:
                pass
        if self.pending_open:
            files, self.pending_open = self.pending_open, []
            self.open_paths(files)

    def _setup_thumbbar(self):
        if not self.taskbar or self.taskbar.added:
            return
        color = T.INK if W.system_light_theme() else T.WHITE
        for name in ("prev", "play", "pause", "next"):
            self.thumb_icons[name] = W.hicon_from_qimage(T.svg_image(name, color, 32))
        self._update_thumbbar()

    def _update_thumbbar(self):
        if not self.taskbar or not self.thumb_icons:
            return
        playing = self.is_playing()
        has = self.current is not None
        self.taskbar.set_buttons([
            (101, self.thumb_icons["prev"], "Previous", has),
            (102, self.thumb_icons["pause" if playing else "play"], "Pause" if playing else "Play", True),
            (103, self.thumb_icons["next"], "Next", has),
        ])

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == W.WM_HOTKEY:
            {1: self.toggle_play, 2: self.next, 3: self.prev, 4: self.stop}.get(msg.wParam, lambda: None)()
            return True, 0
        if msg.message == W.TASKBAR_CREATED:
            if self.taskbar:
                self.taskbar.added = False
            QTimer.singleShot(0, self._setup_thumbbar)
        elif msg.message == W.WM_COMMAND and ((msg.wParam >> 16) & 0xFFFF) == W.THBN_CLICKED:
            {101: self.prev, 102: self.toggle_play, 103: self.next}.get(msg.wParam & 0xFFFF, lambda: None)()
            return True, 0
        return False, 0

    # ================================================================ library
    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scanbar.show()
        self.scan_text.setText("Looking through your folders…")
        self._update_empty()
        self.scanner = Scanner(self.s["folders"], self)
        self.scanner.progress.connect(lambda n, d: self.scan_text.setText(f"Scanning…  {n:,} found  ·  {d}"))
        self.scanner.partial.connect(lambda items: (not self.items or self.view.verticalScrollBar().value() == 0)
                                     and self.set_library(items))
        self.scanner.done.connect(self._scan_done)
        self.scanner.start()

    def _scan_done(self, items):
        self.scanning = False
        self.scanbar.hide()
        self.set_library(items)
        self._update_empty()

    def set_library(self, items):
        sig = (len(items), sum(int(i.mtime) + len(i.path) for i in items))
        if sig == self.signature:
            return
        self.signature = sig
        self.items = items
        self.by_path = {i.path.lower(): i for i in items}
        counts = {"all": len(items), "video": 0, "audio": 0, "image": 0}
        for i in items:
            counts[i.type] = counts.get(i.type, 0) + 1
        for k, lbl in self.counts.items():
            lbl.setText(f"{counts.get(k, 0):,}" if counts.get(k) else "")
        self._render_folders()
        if self.pages.currentWidget() is not self.page_settings:
            self.refresh()

    def _render_folders(self):
        while self.folder_layout.count():
            w = self.folder_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        counts = {}
        for i in self.items:
            counts[i.root] = counts.get(i.root, 0) + 1
        self.folder_buttons = {}
        for f in self.s["folders"]:
            name = os.path.basename(f.rstrip("\\/")) or f
            b = self._nav_button("folder", name)
            b.setToolTip(f)
            b.setMinimumHeight(36)
            b.setChecked(self.view_name == "folder" and self.folder == f)
            c = QLabel(f"{counts.get(f, 0):,}" if counts.get(f) else "", objectName="Count")
            c.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay = QHBoxLayout(b)
            lay.setContentsMargins(0, 0, 12, 0)
            lay.addStretch()
            lay.addWidget(c)
            b.clicked.connect(lambda _=False, ff=f: self.set_view("folder", ff))
            self.folder_layout.addWidget(b)
            self.folder_buttons[f] = b
        if self.pages.currentWidget() is self.page_settings:
            self._render_settings()

    def set_view(self, name, folder=None):
        self.view_name = name if name != "settings" else self.view_name
        if name == "settings":
            for k, b in self.nav.items():
                b.setChecked(k == "settings")
            for b in list(getattr(self, "folder_buttons", {}).values()) + list(self.playlist_buttons.values()):
                b.setChecked(False)
            self._render_settings()
            self.show_page("settings")
            return
        self.folder = folder
        for k, b in self.nav.items():
            b.setChecked(k == name)
        for pid, b in self.playlist_buttons.items():
            b.setChecked(name == "playlist" and pid == folder)
        self.pl_actions.setVisible(name == "playlist")
        self.sort.setVisible(name not in ("playlist", "recent"))
        for f, b in getattr(self, "folder_buttons", {}).items():
            b.setChecked(name == "folder" and f == folder)
        self.eyebrow.setText(VIEW_EYEBROW.get(name, ""))
        if name == "playlist":
            pl = self.playlists.get(folder)
            self.title.setText(pl["name"] if pl else "Playlist")
        else:
            self.title.setText(os.path.basename(folder.rstrip("\\/")) if name == "folder" else VIEW_TITLE[name])
        self.show_page("library")
        self.refresh()

    def _compute_list(self):
        v = self.view_name
        if v == "recent":
            lst = []
            for p in self.s["recent"]:
                it = self.by_path.get(p.lower()) or (Item.from_url(p) if "://" in p else Item.from_path(p))
                if it:
                    lst.append(it)
        elif v == "playlist":
            lst = self._playlist_items(self.folder)
        elif v == "folder":
            lst = [i for i in self.items if i.root == self.folder]
        elif v == "all":
            lst = list(self.items)
        else:
            lst = [i for i in self.items if i.type == v]
        if self.query:
            q = self.query.casefold()
            lst = [i for i in lst if q in i.name.casefold() or q in i.dir.casefold()]
        if v not in ("recent", "playlist"):
            key = self.s["sort"]
            if key == "name":
                lst.sort(key=lambda i: i.natural_key)
            elif key == "newest":
                lst.sort(key=lambda i: -i.mtime)
            elif key == "oldest":
                lst.sort(key=lambda i: i.mtime)
            elif key == "largest":
                lst.sort(key=lambda i: -i.size)
            elif key == "type":
                lst.sort(key=lambda i: (i.type, i.natural_key))
        return lst

    def refresh(self):
        lst = self._compute_list()
        self.model.set_items(lst)
        n = len(lst)
        sub = f"{n:,} item{'s' if n != 1 else ''}"
        if self.view_name == "playlist":
            sub += "  ·  right-click an item to move or remove it"
        if self.view_name == "folder" and self.folder:
            sub += f"  ·  {self.folder}"
        self.subtitle.setText(sub)
        self._update_empty()

    def _update_empty(self):
        empty = self.model.rowCount() == 0
        self.lib_stack.setCurrentIndex(1 if empty else 0)
        self.view._update_grid()
        if not empty:
            return
        if self.scanning:
            t, d = "Looking for your media…", "This only takes a moment."
        elif self.query:
            t, d = "No matches", f"Nothing matches “{self.query}”."
        elif self.view_name == "recent":
            t, d = "Nothing played yet", "The things you play will show up here."
        else:
            t, d = "Nothing here yet", "Add a folder, open files, or drop something into this window."
        self.empty_title.setText(t)
        self.empty_text.setText(d)

    def _apply_search(self):
        self.query = self.search.text().strip()
        self.refresh()

    def _sort_changed(self):
        self._set_setting("sort", self.sort.currentData())
        self.refresh()

    def set_layout(self, layout, save=True):
        self.btn_grid.setChecked(layout != "list")
        self.btn_list.setChecked(layout == "list")
        self.view.set_layout(layout)
        if save:
            self._set_setting("layout", layout)

    def _thumb_ready(self, path):
        self.model.refresh_path(path)
        if self.current and self.current.path == path:
            self._update_art()

    def focus_search(self):
        if self.pages.currentWidget() is not self.page_library:
            self.set_view(self.view_name if self.view_name != "folder" else "all", self.folder)
        self.search.setFocus()
        self.search.selectAll()

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add a folder to your library")
        if not d:
            return
        d = os.path.normpath(d)
        if all(d.lower() != f.lower() for f in self.s["folders"]):
            self.s["folders"].append(d)
            self.save_timer.start()
        self._render_folders()
        self.signature = None
        self.scan()

    def remove_folder(self, f):
        self.s["folders"] = [x for x in self.s["folders"] if x != f]
        self.save_timer.start()
        self.signature = None
        self._render_folders()
        self.scan()

    def _item_menu(self, pos):
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        it = self.model.items[idx.row()]
        m = menu(self)
        m.addAction(T.icon("play", T.INK, 14), "Play", lambda: self.play_list(self.model.items, idx.row()))
        m.addAction(T.icon("mini", T.GRAY, 16), "Play in mini player",
                    lambda: (self.play_list(self.model.items, idx.row()), self.enter_mini()))
        m.addAction("Play next", lambda: self.play_next(it))
        m.addAction(T.icon("queue", T.GRAY, 16), "Add to queue", lambda: self.enqueue(it))
        self._add_to_playlist_menu(m, [it.path])
        if self.view_name == "playlist" and self.folder:
            m.addSeparator()
            m.addAction("Move up", lambda: self._move_in_playlist(it, -1))
            m.addAction("Move down", lambda: self._move_in_playlist(it, 1))
            m.addAction(T.icon("x", T.GRAY, 16), "Remove from this playlist", lambda: self._remove_from_playlist(it))
        m.addSeparator()
        if not it.url:
            m.addAction(T.icon("folder", T.GRAY, 16), "Show in File Explorer", lambda: W.show_in_explorer(it.path))
            m.addAction("Properties", lambda: W.show_properties(it.path))
        m.addAction("Copy path", lambda: QApplication.clipboard().setText(it.path))
        loc = m.addAction(it.dir if not it.url else it.path)
        loc.setEnabled(False)
        m.exec(self.view.viewport().mapToGlobal(pos))

    # ================================================================ playlists
    def _add_to_playlist_menu(self, parent, paths):
        sub = submenu(parent, "Add to playlist")
        sub.setIcon(T.icon("list", T.GRAY, 16))
        sub.addAction(T.icon("plus", T.GRAY, 16), "New playlist…", lambda: self.new_playlist(paths))
        if self.playlists.items:
            sub.addSeparator()
        for pl in self.playlists.items:
            sub.addAction(pl["name"], lambda _=False, pid=pl["id"]: self.add_to_playlist(pid, paths))
        return sub

    def _render_playlists(self):
        while self.playlist_layout.count():
            w = self.playlist_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.playlist_buttons = {}
        for pl in self.playlists.items:
            b = self._nav_button("list", pl["name"])
            b.setMinimumHeight(36)
            b.setChecked(self.view_name == "playlist" and self.folder == pl["id"])
            c = QLabel(f"{len(pl['paths']):,}" if pl["paths"] else "", objectName="Count")
            c.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay = QHBoxLayout(b)
            lay.setContentsMargins(0, 0, 12, 0)
            lay.addStretch()
            lay.addWidget(c)
            b.clicked.connect(lambda _=False, pid=pl["id"]: self.set_view("playlist", pid))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _p, pid=pl["id"]: self._playlist_button_menu(pid))
            self.playlist_layout.addWidget(b)
            self.playlist_buttons[pl["id"]] = b
        if not self.playlists.items:
            hint = QLabel("Click + or right-click any file\n→ Add to playlist", objectName="Hint")
            hint.setStyleSheet("font-size: 11px;")
            hint.setContentsMargins(14, 0, 0, 4)
            self.playlist_layout.addWidget(hint)

    def _playlist_button_menu(self, pid):
        m = menu(self)
        m.addAction(T.icon("play", T.INK, 14), "Play", lambda: self.play_playlist(pid))
        m.addAction("Rename…", lambda: self.rename_playlist(pid))
        m.addAction("Export as .m3u…", lambda: self.export_playlist(pid))
        m.addSeparator()
        m.addAction(T.icon("trash", T.GRAY, 16), "Delete", lambda: self.delete_playlist(pid))
        m.exec(QCursor.pos())

    def _playlist_items(self, pid):
        pl = self.playlists.get(pid)
        out = []
        for p in (pl["paths"] if pl else []):
            it = self.by_path.get(p.lower()) or (Item.from_url(p) if "://" in p else Item.from_path(p))
            if it:
                out.append(it)
        return out

    def new_playlist(self, paths=None):
        name, ok = QInputDialog.getText(self, "New playlist", "Name your playlist:",
                                        text=self.playlists.unique_name("My playlist"))
        if not ok:
            return
        pl = self.playlists.create(name, paths or [])
        self._render_playlists()
        self.toast.show_msg(f"Created “{pl['name']}”" + (f" with {len(pl['paths'])} items" if pl["paths"] else ""))
        if not paths:
            self.set_view("playlist", pl["id"])

    def add_to_playlist(self, pid, paths):
        n = self.playlists.add(pid, paths)
        pl = self.playlists.get(pid)
        self._render_playlists()
        self.toast.show_msg(f"Added to “{pl['name']}”" if n else f"Already in “{pl['name']}”")
        if self.view_name == "playlist" and self.folder == pid:
            self.refresh()

    def _remove_from_playlist(self, it):
        self.playlists.remove(self.folder, it.path)
        self._render_playlists()
        self.refresh()

    def _move_in_playlist(self, it, delta):
        self.playlists.move(self.folder, it.path, delta)
        self.refresh()

    def play_playlist(self, pid):
        items = self._playlist_items(pid)
        if items:
            self.play_list(items, 0)
        else:
            self.toast.show_msg("This playlist is empty")

    def shuffle_view(self):
        if not self.model.items:
            return
        if not self.s["shuffle"]:
            self.toggle_shuffle()
        self.play_list(self.model.items, random.randrange(len(self.model.items)))

    def rename_playlist(self, pid):
        pl = self.playlists.get(pid)
        if not pl:
            return
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:", text=pl["name"])
        if ok and name.strip():
            self.playlists.rename(pid, name)
            self._render_playlists()
            if self.view_name == "playlist" and self.folder == pid:
                self.title.setText(pl["name"])

    def delete_playlist(self, pid):
        pl = self.playlists.get(pid)
        if not pl:
            return
        ask = QMessageBox.question(self, "Delete playlist", f"Delete “{pl['name']}”?\nYour files are not touched.")
        if ask != QMessageBox.Yes:
            return
        self.playlists.delete(pid)
        self._render_playlists()
        if self.view_name == "playlist" and self.folder == pid:
            self.set_view("all")

    def export_playlist(self, pid):
        pl = self.playlists.get(pid)
        if not pl:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Export playlist", pl["name"] + ".m3u", "M3U playlist (*.m3u)")
        if dest:
            self.playlists.export_m3u(pid, dest)
            self.toast.show_msg("Playlist exported")

    def import_playlist(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import playlist", "", "Playlists (*.m3u *.m3u8 *.pls *.xspf)")
        if not f:
            return
        items = items_from_paths([os.path.normpath(f)])
        pl = self.playlists.create(os.path.splitext(os.path.basename(f))[0], [i.path for i in items])
        self._render_playlists()
        self.set_view("playlist", pl["id"])
        self.toast.show_msg(f"Imported {len(items)} items")

    def reveal_current(self):
        if self.current and not self.current.url:
            W.show_in_explorer(self.current.path)

    # ================================================================ settings page
    def _set_setting(self, key, value):
        self.s[key] = value
        self.save_timer.start()
        if key == "media_keys":
            hwnd = int(self.winId())
            W.register_media_keys(hwnd) if value else W.unregister_media_keys(hwnd)

    def _render_settings(self):
        while self.settings_folders.count():
            w = self.settings_folders.takeAt(0).widget()
            if w:
                w.deleteLater()
        for f in self.s["folders"]:
            row = QFrame(objectName="FolderRow")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 6, 6, 6)
            ic = QLabel()
            ic.setPixmap(T.pixmap("folder", T.GOLD, 18))
            h.addWidget(ic)
            lbl = QLabel(f)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            h.addWidget(lbl, 1)
            rm = tool("trash", "Remove from library", T.MUTED, 16)
            rm.clicked.connect(lambda _=False, ff=f: self.remove_folder(ff))
            h.addWidget(rm)
            self.settings_folders.addWidget(row)
        if not self.s["folders"]:
            self.settings_folders.addWidget(QLabel("No folders yet.", objectName="Hint"))
        self._render_default_status()

    def _render_default_status(self):
        st = W.default_status()
        text = {
            "registered": "✓  Registered with Windows. Choose YouTown Player for each file type in Default apps.",
            "stale": "Registered from another location. Click “Set as default app…” to update it.",
            "none": "Not registered yet.",
        }[st]
        if st != "registered" and not FROZEN:
            text += "  (You're running the developer version; the installed app registers itself.)"
        self.default_status.setText(text)

    def set_default(self):
        try:
            W.register_default()
            W.open_default_apps()
            self.toast.show_msg("Windows Settings opened. Pick YouTown Player for your file types ♡", 4000)
        except Exception as ex:
            self.toast.show_msg(f"Couldn't register: {ex}")
        self._render_default_status()

    def remove_default(self):
        W.unregister_default()
        self._render_default_status()
        self.toast.show_msg("Removed YouTown Player from Windows file associations")

    # ================================================================ pages / queue
    def show_page(self, name):
        target = {"library": self.page_library, "player": self.page_player, "settings": self.page_settings}[name]
        self.pages.setCurrentWidget(target)
        if name != "settings":
            self.nav["settings"].setChecked(False)
            if name == "library":
                for k, b in self.nav.items():
                    b.setChecked(k == self.view_name)
        if name == "player":
            self.preview_dismissed = False
            for k, b in self.nav.items():
                b.setChecked(k == "now")
            for b in list(getattr(self, "folder_buttons", {}).values()) + list(self.playlist_buttons.values()):
                b.setChecked(False)
        else:
            self.nav["now"].setChecked(False)
        self.btn_stage.setChecked(name == "player")
        self._update_preview()

    def _toggle_stage(self):
        if not self.current:
            self.toast.show_msg("Nothing is playing yet")
            return
        self.show_page("library" if self.pages.currentWidget() is self.page_player else "player")

    def toggle_queue(self, on=None):
        on = not self.queue_panel.isVisible() if on is None else on
        self.queue_panel.setVisible(on)
        self.btn_queue.setChecked(on)
        if on:
            self._render_queue()

    def _render_queue(self):
        if not self.queue_panel.isVisible():
            return
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for i, it in enumerate(self.queue):
            li = QListWidgetItem(("♪  " if i == self.qi else "") + it.title)
            li.setData(Qt.UserRole, it)
            li.setToolTip(it.path)
            if i == self.qi:
                f = li.font()
                f.setBold(True)
                li.setFont(f)
                li.setForeground(QColor(T.GOLD))
            self.queue_list.addItem(li)
        self.queue_list.blockSignals(False)
        if 0 <= self.qi < self.queue_list.count():
            self.queue_list.scrollToItem(self.queue_list.item(self.qi), QAbstractItemView.PositionAtCenter)

    def _queue_reordered(self, *args):
        cur = self.queue[self.qi] if 0 <= self.qi < len(self.queue) else None
        self.queue = [self.queue_list.item(i).data(Qt.UserRole) for i in range(self.queue_list.count())]
        self.qi = next((i for i, it in enumerate(self.queue) if it is cur), -1)
        QTimer.singleShot(0, self._render_queue)

    def _play_queue_row(self, row):
        if 0 <= row < len(self.queue):
            self.history.append(self.qi)
            self.qi = row
            self.load(self.queue[row], True)

    def _queue_menu(self, pos):
        li = self.queue_list.itemAt(pos)
        if not li:
            return
        row = self.queue_list.row(li)
        m = menu(self)
        m.addAction("Play", lambda: self._play_queue_row(row))
        m.addAction("Remove from queue", lambda: self._remove_queue_row(row))
        m.exec(self.queue_list.viewport().mapToGlobal(pos))

    def _remove_queue_row(self, row):
        if row == self.qi:
            return self.toast.show_msg("That one is playing right now")
        del self.queue[row]
        if row < self.qi:
            self.qi -= 1
        self._render_queue()

    def clear_queue(self):
        if self.current and 0 <= self.qi < len(self.queue):
            self.queue = [self.queue[self.qi]]
            self.qi = 0
        else:
            self.queue, self.qi = [], -1
        self._render_queue()

    # ================================================================ opening
    def open_paths(self, paths):
        if not self.engine and not hasattr(self, "_engine_tried"):
            self.pending_open += paths
            return
        subs = [p for p in paths if ext_of(p) in SUBTITLE]
        if subs and len(subs) == len(paths) and self.engine and self.current:
            for p in subs:
                self.engine.add_subtitle(p)
            self.toast.show_msg("Subtitle added")
            return
        items = items_from_paths([p for p in paths if ext_of(p) not in SUBTITLE])
        if items:
            self.play_list(items, 0)
        else:
            self.toast.show_msg("Nothing playable there")

    def open_files(self):
        exts = " ".join(f"*.{e}" for e in sorted(OPENABLE))
        files, _ = QFileDialog.getOpenFileNames(self, "Open media", "", f"Media files ({exts});;All files (*.*)")
        if files:
            self.open_paths([os.path.normpath(f) for f in files])

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Play a folder")
        if d:
            self.open_paths([os.path.normpath(d)])

    def open_url(self):
        url, ok = QInputDialog.getText(self, "Open network stream", "Enter a URL (http, https, rtsp, mms, udp, rtp…):")
        url = url.strip()
        if ok and url:
            if "://" not in url:
                url = "http://" + url
            self.play_list([Item.from_url(url)], 0)

    def add_subtitle_file(self):
        if not (self.engine and self.current):
            return self.toast.show_msg("Play a video first")
        exts = " ".join(f"*.{e}" for e in sorted(SUBTITLE))
        f, _ = QFileDialog.getOpenFileName(self, "Add subtitle", os.path.dirname(self.current.path) if not self.current.url else "",
                                           f"Subtitles ({exts});;All files (*.*)")
        if f:
            ok = self.engine.add_subtitle(os.path.normpath(f))
            self.toast.show_msg("Subtitle added" if ok else "Couldn't load that subtitle")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for u in e.mimeData().urls():
            paths.append(os.path.normpath(u.toLocalFile()) if u.isLocalFile() else u.toString())
        if paths:
            self.open_paths(paths)

    # ================================================================ playback
    def is_playing(self):
        if not self.current:
            return False
        if self.qt_image:
            return self.slide_timer.isActive()
        return bool(self.engine and self.engine.is_playing())

    def play_list(self, items, idx):
        if not items:
            return
        self.queue = list(items)
        self.qi = max(0, min(idx, len(items) - 1))
        self.history = []
        it = self.queue[self.qi]
        self.load(it, autoplay=it.type != "image")
        if it.type in ("video", "image"):
            self.show_page("player")

    def load(self, item, autoplay=True):
        self._save_position()
        self.slide_timer.stop()
        self.current = item
        self.ab = [None, None]
        self.act_ab.setText("A→B loop: set start")
        self.pending_resume = None
        self.vol_applied = False
        self.meta_done = False
        self.error_handled = False
        self.last_sec = -1
        self.play_started = time.monotonic()
        self.stage_title.setText(item.title)
        self.preview_dismissed = False
        self.nav["now"].show()
        self.stage_path.setText(" " + (item.path if item.url else item.dir))
        self.stage_path.setToolTip(item.path)

        self.qt_image = item.type == "image" and not item.url and ImageView.can_read(item.path)
        if self.qt_image:
            if self.engine:
                self.engine.stop()
            self.image_view.set_path(item.path)
            self._set_stage("image")
            if autoplay:
                self.slide_timer.start(int(self.s["slide_interval"]) * 1000)
        else:
            self.image_view.clear()
            if not self.engine:
                self.toast.show_msg("The playback engine isn't available (is VLC installed?)")
                return
            self.engine.open(item.path, item.url)
            self.engine.set_rate(self.speed)
            self.engine.set_aspect(self.aspect)
            if self.eq_index >= 0:
                self.engine.set_eq_preset(self.eq_index)
            if autoplay:
                self.engine.play()
            self._set_stage("audio" if item.type == "audio" else "video")
            if self.s["resume"] and not item.url:
                self.pending_resume = self.s["positions"].get(item.path)

        self.seek.setEnabled(not self.qt_image)
        self.seek.blockSignals(True)
        self.seek.setValue(0)
        self.seek.blockSignals(False)
        self.t_cur.setText("" if self.qt_image else "0:00")
        self.t_dur.setText("" if self.qt_image else "0:00")
        self.np_title.setText(item.title)
        self.np_title.setToolTip(item.path)
        kind = {"video": "Video", "audio": "Music", "image": "Image"}.get(item.type, "")
        sub = "Stream" if item.url else f"{kind}  ·  {os.path.basename(item.dir)}"
        self.np_sub.setText(sub)
        self.np_sub.setToolTip(("Location: " + item.path + "\nClick to show in File Explorer") if not item.url else item.path)
        self.audio_view.set_info(item.title, "" if item.url else os.path.basename(item.dir))
        self._update_art()
        self._add_recent(item)
        self.view.viewport().update()
        self._render_queue()
        self._update_play_state()

    def _update_art(self, art_pm=None):
        it = self.current
        if not it:
            return
        pm = art_pm or self.thumbs.get(it)
        if pm is not None:
            self.np_art.setPixmap(rounded(pm, 54, 12))
            if it.type == "audio":
                self.audio_view.art = pm
                self.audio_view.update()
        else:
            self.np_art.setPixmap(T.pixmap(it.type if it.type in ("video", "audio", "image") else "video", T.MAUVE, 22))

    def _add_recent(self, item):
        r = [p for p in self.s["recent"] if p != item.path]
        r.insert(0, item.path)
        self.s["recent"] = r[:80]
        self.save_timer.start()

    def _save_position(self):
        it = self.current
        if not (it and self.engine and not self.qt_image and not it.url):
            return
        length, t = self.engine.length(), self.engine.time()
        pos = self.s["positions"]
        if length > 180_000 and 15_000 < t < length - 20_000:
            pos.pop(it.path, None)
            pos[it.path] = t
            while len(pos) > 300:
                pos.pop(next(iter(pos)))
        else:
            pos.pop(it.path, None)
        self.save_timer.start()

    def toggle_play(self):
        if not self.current:
            if self.model.items:
                self.play_list(self.model.items, 0)
            return
        if self.qt_image:
            if self.slide_timer.isActive():
                self.slide_timer.stop()
            else:
                self.slide_timer.start(int(self.s["slide_interval"]) * 1000)
        elif self.engine:
            self.engine.toggle()
        QTimer.singleShot(60, self._update_play_state)

    def stop(self):
        self.slide_timer.stop()
        if self.engine and not self.qt_image:
            self._save_position()
            self.engine.stop()
        self.seek.setValue(0)
        self.t_cur.setText("0:00" if not self.qt_image else "")
        QTimer.singleShot(60, self._update_play_state)

    def next(self, auto=False, skip_repeat=False):
        if not self.queue:
            return
        was = auto or self.is_playing()
        if auto and self.s["repeat"] == "one" and not skip_repeat:
            return self.load(self.current, True)
        if self.s["shuffle"] and len(self.queue) > 1:
            i = self.qi
            while i == self.qi:
                i = random.randrange(len(self.queue))
        else:
            i = self.qi + 1
            if i >= len(self.queue):
                if auto and self.s["repeat"] != "all":
                    self.slide_timer.stop()
                    self._update_play_state()
                    return
                i = 0
        self.history.append(self.qi)
        self.qi = i
        self.load(self.queue[i], was)

    def prev(self):
        if not self.queue:
            return
        if self.engine and not self.qt_image and self.engine.time() > 3000:
            self.engine.set_time(0)
            return
        was = self.is_playing()
        if self.s["shuffle"] and self.history:
            i = self.history.pop()
        else:
            i = (self.qi - 1) % len(self.queue)
        self.qi = i
        self.load(self.queue[i], was)

    def play_next(self, item):
        if not self.current:
            return self.play_list([item], 0)
        self.queue.insert(self.qi + 1, item)
        self._render_queue()
        self.toast.show_msg(f"“{item.title}” plays next")

    def enqueue(self, item):
        if not self.current:
            return self.play_list([item], 0)
        self.queue.append(item)
        self._render_queue()
        self.toast.show_msg(f"Added “{item.title}” to the queue")

    def jump(self, ms):
        if self.qt_image:
            return self.next() if ms > 0 else self.prev()
        if self.engine and self.current and self.engine.seekable():
            length = self.engine.length()
            t = max(0, min(length - 500 if length else 10**12, self.engine.time() + ms))
            self.engine.set_time(t)
            self.toast.show_msg(f"{'+' if ms > 0 else '−'}{abs(ms) // 1000} s   ·   {fmt_time(t)}", 900)

    def _seek_to(self, v):
        if self.engine and not self.qt_image and self.engine.length() > 0:
            self.engine.set_time(self.engine.length() * v / 10000)

    def _seek_preview(self, v):
        if self.seek.dragging and self.engine and self.engine.length() > 0:
            self.t_cur.setText(fmt_time(self.engine.length() * v / 10000))

    def show_time(self):
        if self.engine and self.current and not self.qt_image:
            self.toast.show_msg(f"{fmt_time(self.engine.time())}  /  {fmt_time(self.engine.length())}", 1500)

    def jump_to_time(self):
        if not (self.engine and self.current and not self.qt_image):
            return
        text, ok = QInputDialog.getText(self, "Jump to time", "Time (e.g. 1:23 or 1:02:03):",
                                        text=fmt_time(self.engine.time()))
        if not ok:
            return
        parts = [p for p in re.split(r"[:\s]", text.strip()) if p]
        try:
            secs = 0
            for p in parts:
                secs = secs * 60 + float(p)
            self.engine.set_time(secs * 1000)
        except ValueError:
            self.toast.show_msg("That doesn't look like a time")

    def frame_step(self):
        if self.engine and self.current and not self.qt_image:
            self.engine.next_frame()

    def set_speed(self, sp):
        self.speed = sp
        if self.engine:
            self.engine.set_rate(sp)
        self.btn_speed.setText(f"{sp:g}×")
        for a in self.speed_group.actions():
            a.setChecked(a.data() == sp)
        self.toast.show_msg(f"Speed {sp:g}×", 900)

    def step_speed(self, d):
        i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - self.speed))
        self.set_speed(SPEEDS[max(0, min(len(SPEEDS) - 1, i + d))])

    def set_aspect(self, a):
        self.aspect = a
        if self.engine:
            self.engine.set_aspect(a)
        self.toast.show_msg(f"Aspect ratio: {a}", 1000)

    def cycle_aspect(self):
        self.set_aspect(ASPECTS[(ASPECTS.index(self.aspect) + 1) % len(ASPECTS)])

    def set_eq(self, i):
        self.eq_index = i
        if self.engine:
            self.engine.set_eq_preset(i)
        self.toast.show_msg("Equalizer off" if i < 0 else f"Equalizer: {self.engine.eq_presets()[i]}", 1200)

    def cycle_track(self, kind):
        if not (self.engine and self.current):
            return
        tracks = self.engine.audio_tracks() if kind == "audio" else self.engine.sub_tracks()
        if not tracks:
            return self.toast.show_msg("No subtitles" if kind == "sub" else "No audio tracks", 1000)
        cur = self.engine.audio_track() if kind == "audio" else self.engine.sub_track()
        ids = [t for t, _ in tracks]
        i = (ids.index(cur) + 1) % len(ids) if cur in ids else 0
        (self.engine.set_audio_track if kind == "audio" else self.engine.set_sub_track)(ids[i])
        self.toast.show_msg(("Audio: " if kind == "audio" else "Subtitles: ") + tracks[i][1], 1200)

    def nudge_delay(self, kind, ms):
        if not self.engine:
            return
        get, put = ((self.engine.audio_delay, self.engine.set_audio_delay) if kind == "audio"
                    else (self.engine.sub_delay, self.engine.set_sub_delay))
        val = 0 if ms is None else get() + ms
        put(val)
        self.toast.show_msg(f"{'Audio' if kind == 'audio' else 'Subtitle'} delay {val:+d} ms", 1000)

    def ab_loop(self):
        if not (self.engine and self.current and not self.qt_image):
            return
        if self.ab[0] is None:
            self.ab[0] = self.engine.time()
            self.act_ab.setText("A→B loop: set end")
            self.toast.show_msg(f"Loop start  {fmt_time(self.ab[0])}")
        elif self.ab[1] is None:
            t = self.engine.time()
            if t <= self.ab[0]:
                return self.toast.show_msg("The end has to come after the start")
            self.ab[1] = t
            self.act_ab.setText("A→B loop: clear")
            self.toast.show_msg(f"Looping  {fmt_time(self.ab[0])} → {fmt_time(self.ab[1])}")
        else:
            self.ab = [None, None]
            self.act_ab.setText("A→B loop: set start")
            self.toast.show_msg("Loop cleared")

    def snapshot(self):
        if not (self.engine and self.current and self.current.type == "video" and not self.qt_image):
            return self.toast.show_msg("Snapshots work while a video plays")
        pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        out_dir = Path(pics) / "YouTown Snapshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|]+', "_", self.current.title)[:60]
        path = out_dir / f"{safe} {fmt_time(self.engine.time()).replace(':', '-')}.png"
        ok = self.engine.snapshot(path)
        self.toast.show_msg(f"Snapshot saved to Pictures › YouTown Snapshots" if ok else "Couldn't take a snapshot", 2500)

    def set_on_top(self, on):
        hwnd = int(self.winId())
        ctypes.windll.user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(-1 if on else -2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    # ------------------------------------------------------------ volume / modes
    def _volume_changed(self, v):
        self.s["volume"] = v
        if v > 0 and self.s["muted"]:
            self.s["muted"] = False
        self._apply_volume()
        self._render_volume()
        self.save_timer.start()

    def _apply_volume(self):
        if self.engine:
            self.engine.set_volume(self.s["volume"])
            self.engine.set_mute(self.s["muted"])

    def nudge_volume(self, d):
        self.volume.setValue(max(0, min(125, self.volume.value() + d)))
        self.toast.show_msg(f"Volume {self.volume.value()}%", 800)

    def _wheel(self, d):
        if self.qt_image:
            self.next() if d < 0 else self.prev()
        else:
            self.nudge_volume(5 * d)

    def toggle_mute(self):
        self.s["muted"] = not self.s["muted"]
        self._apply_volume()
        self._render_volume()
        self.save_timer.start()

    def _render_volume(self):
        v, m = self.s["volume"], self.s["muted"]
        name = "volX" if m or v == 0 else ("volLow" if v < 50 else "vol")
        self.btn_mute.setIcon(T.icon(name, T.GRAY, 19, T.INK))

    def toggle_shuffle(self):
        self.s["shuffle"] = not self.s["shuffle"]
        self._render_modes()
        self.save_timer.start()
        self.toast.show_msg("Shuffle on" if self.s["shuffle"] else "Shuffle off", 900)

    def cycle_repeat(self):
        order = ["off", "all", "one"]
        self.s["repeat"] = order[(order.index(self.s["repeat"]) + 1) % 3]
        self._render_modes()
        self.save_timer.start()
        self.toast.show_msg({"off": "Repeat off", "all": "Repeat all", "one": "Repeat one"}[self.s["repeat"]], 900)

    def _render_modes(self):
        self.btn_shuffle.setChecked(bool(self.s["shuffle"]))
        r = self.s["repeat"]
        self.btn_repeat.setIcon(T.icon("repeat1" if r == "one" else "repeat", T.GOLD if r != "off" else T.MUTED, 18, T.INK))
        self.btn_repeat.setToolTip({"off": "Repeat: off (L)", "all": "Repeat: all (L)", "one": "Repeat: one (L)"}[r])

    # ------------------------------------------------------------ fullscreen
    def toggle_fullscreen(self):
        if self.mini_active:
            self.exit_mini()
        if self.isFullScreen():
            self._exit_fullscreen()
            return
        if not self.current:
            return
        self.show_page("player")
        self._was_max = self.isMaximized()
        self._queue_was = self.queue_panel.isVisible()
        self.sidebar.hide()
        self.player_top.hide()
        self.queue_panel.hide()
        self.showFullScreen()
        self.btn_full.setIcon(T.icon("unfull", T.GRAY, 18, T.INK))
        self.last_move = time.monotonic()

    def _exit_fullscreen(self):
        self.sidebar.show()
        self.player_top.show()
        self.bar.show()
        self.queue_panel.setVisible(getattr(self, "_queue_was", False))
        self.showMaximized() if getattr(self, "_was_max", False) else self.showNormal()
        self.btn_full.setIcon(T.icon("full", T.GRAY, 18, T.INK))
        self.unsetCursor()

    def escape(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        elif self.search.hasFocus():
            self.search.clear()
            self.view.setFocus()
        elif self.pages.currentWidget() is not self.page_library:
            self.show_page("library")

    # ------------------------------------------------------------ poll loop
    def _poll(self):
        now = time.monotonic()
        if self.isFullScreen():
            pos = QCursor.pos()
            if pos != self.last_cursor:
                self.last_cursor = pos
                self.last_move = now
                if not self.bar.isVisible():
                    self.bar.show()
            elif now - self.last_move > 2.5 and self.is_playing() and self.bar.isVisible() \
                    and not self.bar.geometry().contains(self.mapFromGlobal(pos)):
                self.bar.hide()

        if not (self.engine and self.current) or self.qt_image:
            self._sync_play_state()
            return
        st = self.engine.state()
        if st == "ended":
            self.s["positions"].pop(self.current.path, None)
            if self.last_sec <= 0 and now - self.play_started < 3:
                # ended instantly: broken or unsupported file; skip it even on repeat-one
                self.fail_count += 1
                self.toast.show_msg(f"Couldn't play “{self.current.title}”", 2500)
                if self.fail_count >= len(self.queue):
                    self.fail_count = 0
                    self.engine.stop()
                    self._update_play_state()
                    return
                self.next(auto=True, skip_repeat=True)
                return
            self.next(auto=True)
            return
        if st == "error":
            if not self.error_handled:
                self.error_handled = True
                self.toast.show_msg(f"Couldn't play “{self.current.title}”", 2500)
                if len(self.queue) > 1:
                    QTimer.singleShot(1500, lambda: self.next(auto=True))
            self._sync_play_state()
            return
        if st == "playing" and not self.vol_applied:
            self._apply_volume()
            self.vol_applied = True
        length = self.engine.length()
        t = self.engine.time()
        if self.pending_resume and length > 0:
            if self.pending_resume < length - 20_000:
                self.engine.set_time(self.pending_resume)
                self.toast.show_msg(f"Continuing from {fmt_time(self.pending_resume)}   ·   press P to start over", 3200)
            self.pending_resume = None
        if self.ab[1] is not None and t >= self.ab[1]:
            self.engine.set_time(self.ab[0])
        if length > 0 and not self.seek.dragging:
            self.seek.blockSignals(True)
            self.seek.setValue(int(t * 10000 / length))
            self.seek.blockSignals(False)
        sec = t // 1000
        if sec > 0:
            self.fail_count = 0
        if sec != self.last_sec:
            self.last_sec = sec
            if not self.seek.dragging:
                self.t_cur.setText(fmt_time(t))
            self.t_dur.setText(fmt_time(length) if length else ("LIVE" if self.current.url else "0:00"))
            if self.taskbar and sec % 1 == 0:
                self.taskbar.progress(t, length, paused=st == "paused")
        if not self.meta_done and st == "playing" and now - self.play_started > 0.8:
            self._apply_meta()
        if (self.current.type == "video" and st == "playing" and now - self.play_started > 1.5
                and self.stage_kind == "video" and not self.engine.has_video()):
            self.audio_view.set_info(self.current.title, os.path.basename(self.current.dir) if not self.current.url else "")
            self._set_stage("audio")
        if now - self.last_save > 5:
            self.last_save = now
            self._save_position()
        self._sync_play_state()

    def _apply_meta(self):
        self.meta_done = True
        meta = self.engine.meta()
        it = self.current
        title = meta.get("now") if it.url and meta.get("now") else (meta.get("title") if it.type == "audio" else None)
        if title and not it.url and title in (it.name, it.title):
            title = None  # VLC falls back to the file name; keep our cleaner title
        artist = meta.get("artist")
        if title:
            self.np_title.setText(title)
        if artist and it.type == "audio":
            self.np_sub.setText(artist + (f"  ·  {meta['album']}" if meta.get("album") else ""))
        self.audio_view.set_info(title or it.title, artist or ("" if it.url else os.path.basename(it.dir)), self.audio_view.art)
        art = meta.get("art")
        if art and art.startswith("file:"):
            pm = QPixmap(QUrl(art).toLocalFile())
            if not pm.isNull():
                self.audio_view.art = pm
                self._update_art(pm)

    def _sync_play_state(self):
        playing = self.is_playing()
        if playing != self.last_playing:
            self._update_play_state()

    def _update_play_state(self):
        playing = self.is_playing()
        self.last_playing = playing
        self.btn_play.setIcon(T.icon("pause" if playing else "play", T.WHITE, 20, T.WHITE))
        self.btn_play.setToolTip("Pause (Space)" if playing else "Play (Space)")
        title = self.current.title if self.current else ""
        self.setWindowTitle(f"{title} — {APP_NAME}" if title else APP_NAME)
        self.tray.setToolTip((f"{title} — {APP_NAME}" if title else APP_NAME)[:127])
        self.tray_title.setText(title[:60] or "Nothing playing")
        self.tray_play.setText("Pause" if playing else "Play")
        self._update_thumbbar()
        self.now_dot.setText("♪" if playing else ("❚❚" if self.current else ""))
        self.now_dot.setStyleSheet(f"color: {T.GOLD if playing else T.TAUPE}; font-size: {13 if playing else 9}px;")
        if self.taskbar and (not self.current or self.qt_image):
            self.taskbar.progress(0, 0)
        self.view.viewport().update()

    # ------------------------------------------------------------ window lifecycle
    def bring_to_front(self):
        if self.mini_active:
            return self.exit_mini()
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.quitting = True
        self.close()

    # ------------------------------------------------------------ mini player
    @property
    def mini_active(self):
        return self.mini is not None and self.mini.isVisible()

    def _set_stage(self, kind):
        self.stage_kind = kind
        if self.mini_active:
            self.mini.set_kind(kind)
        else:
            if kind != "video" or self.video_home == "stage":
                self.stage.setCurrentWidget({"video": self.video, "image": self.image_view, "audio": self.audio_view}[kind])
            self._update_preview()

    # ------------------------------------------------------------ getting back to what's playing
    def open_now_playing(self):
        if not self.current:
            return self.toast.show_msg("Nothing is playing yet")
        if self.mini_active:
            return self.exit_mini()
        self.show_page("player")

    def _video_clicked(self):
        if self.mini_active:
            return
        if self.video_home == "preview":
            self.open_now_playing()
        else:
            self.toggle_play()

    def _video_double_clicked(self):
        if self.mini_active:
            self.exit_mini()
        elif self.video_home == "preview":
            self.open_now_playing()
        else:
            self.toggle_fullscreen()

    def _dismiss_preview(self):
        self.preview_dismissed = True
        self._update_preview()
        self.toast.show_msg("Still playing · click the cover below or “Now playing” to watch")

    def _move_video(self, home):
        if self.video_home == home:
            return
        if self.video_home == "stage":
            self.stage.removeWidget(self.video)
        elif self.video_home == "preview":
            self.preview.take_video()
        elif self.video_home == "mini" and self.mini is not None:
            self.mini.detach_video()
        if home == "stage":
            self.stage.insertWidget(0, self.video)
        elif home == "preview":
            self.preview.put_video(self.video)
        elif home == "mini":
            self.mini.attach_video(self.video)
        self.video_home = home
        self.video.show()

    def _update_preview(self):
        if not hasattr(self, "preview") or self.mini_active:
            return
        want = (self.current is not None and self.stage_kind == "video" and not self.qt_image
                and self.pages.currentWidget() is not self.page_player and not self.preview_dismissed
                and not self.isFullScreen())
        if want:
            self._move_video("preview")
            self.preview.title.setText(self.current.title)
            self.preview.show()
            self.preview.place(self.pages.geometry())
        else:
            self.preview.hide()
            self._move_video("stage")
            if self.stage_kind == "video":
                self.stage.setCurrentWidget(self.video)

    def eventFilter(self, obj, e):
        if obj is self.pages and e.type() in (e.Type.Resize, e.Type.Move) and self.preview.isVisible():
            self.preview.place(self.pages.geometry())
        return super().eventFilter(obj, e)

    def enter_mini(self):
        if self.mini_active:
            return
        if not self.current:
            if not self.model.items:
                return self.toast.show_msg("Pick something to play first")
            self.play_list(self.model.items, 0)
        if self.isFullScreen():
            self._exit_fullscreen()
        if self.mini is None:
            self.mini = MiniPlayer(self)
        self.mini.place(self.s.get("mini_geometry"))
        self.preview.hide()
        self._move_video("mini")
        self.mini.show()
        self.mini.set_kind(self.stage_kind)
        self.mini.raise_()
        self.mini.activateWindow()
        self.hide()

    def exit_mini(self):
        if self.mini is None:
            return
        self.s["mini_geometry"] = bytes(self.mini.saveGeometry().toBase64()).decode()
        self.save_timer.start()
        self._move_video("stage")
        self.mini.hide()
        self._set_stage(self.stage_kind)
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.current and self.current.type != "audio":
            self.show_page("player")

    def closeEvent(self, e):
        if self.mini is not None and self.mini.isVisible() and (self.quitting or not self.s["close_to_tray"]):
            self.s["mini_geometry"] = bytes(self.mini.saveGeometry().toBase64()).decode()
            self.mini.hide()
        if self.s["close_to_tray"] and not self.quitting:
            e.ignore()
            self.hide()
            if not self.tray_hinted:
                self.tray_hinted = True
                self.tray.showMessage(APP_NAME, "Still playing here ♡  Right-click the tray icon to quit.",
                                      T.app_icon(), 3000)
            return
        self._save_position()
        if self.scanner and self.scanner.isRunning():
            self.scanner.requestInterruption()
            self.scanner.wait(1500)
        if not self.isFullScreen():
            self.s["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.s.save()
        W.unregister_media_keys(int(self.winId()))
        self.tray.hide()
        if self.engine:
            self.engine.release()
        e.accept()
        QApplication.quit()
