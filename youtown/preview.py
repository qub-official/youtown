"""Floating video preview shown over the library while a video keeps playing. Click it to go back."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout

from . import theme as T

W, H = 344, 194  # 16:9 video area


class PreviewCard(QFrame):
    def __init__(self, parent, on_expand, on_close):
        super().__init__(parent)
        self.setObjectName("PreviewCard")
        self.setStyleSheet(f"""
            #PreviewCard {{ background: {T.INK}; border-radius: 16px; border: 1px solid {T.GRAY}; }}
            #PreviewCard QLabel {{ color: {T.CREAM}; font-size: 11px; font-weight: 600; }}
            #PreviewCard QToolButton {{ border-radius: 9px; padding: 3px; }}
            #PreviewCard QToolButton:hover {{ background: #2A2D33; }}
        """)
        self.setFixedSize(W + 12, H + 46)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(6, 0, 0, 0)
        top.setSpacing(2)
        self.title = QLabel("")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.mousePressEvent = lambda e: on_expand()
        top.addWidget(self.title, 1)
        for icon, tip, fn in (("expand", "Show video", on_expand), ("x", "Hide preview (keeps playing)", on_close)):
            b = QToolButton()
            b.setIcon(T.icon(icon, T.CREAM, 15, T.WHITE))
            b.setIconSize(QSize(15, 15))
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            top.addWidget(b)
        v.addLayout(top)
        self.slot = QVBoxLayout()
        self.slot.setContentsMargins(0, 0, 0, 0)
        v.addLayout(self.slot, 1)
        self.video = None
        self.hide()

    def put_video(self, video):
        self.video = video
        video.setParent(self)
        self.slot.addWidget(video)
        video.show()

    def take_video(self):
        v, self.video = self.video, None
        if v is not None:
            self.slot.removeWidget(v)
        return v

    def place(self, area):
        """area: geometry (in parent coords) of the region to sit in, bottom-right."""
        self.move(area.right() - self.width() - 30, area.bottom() - self.height() - 18)
        self.raise_()
