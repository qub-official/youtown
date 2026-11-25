import getpass
import json
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .config import APP_NAME, Settings
from .formats import OPENABLE, SUBTITLE, ext_of

SERVER = "YouTownPlayer-" + getpass.getuser()


def files_from_argv(argv):
    out = []
    for a in argv[1:]:
        if not a or a.startswith("-"):
            continue
        if "://" in a:
            out.append(a)
            continue
        p = os.path.abspath(a)
        if os.path.isdir(p) or (os.path.isfile(p) and (ext_of(p) in OPENABLE or ext_of(p) in SUBTITLE)):
            out.append(p)
    return out


def main():
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YouTown.Player")
    files = files_from_argv(sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("YouTown")
    app.setQuitOnLastWindowClosed(False)

    # Already running? Hand the files over and leave.
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if sock.waitForConnected(300):
        sock.write(json.dumps(files).encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return 0

    from . import theme
    from .window import MainWindow

    app.setFont(QFont(theme.SANS, 10))
    app.setStyleSheet(theme.QSS)
    app.setWindowIcon(theme.app_icon())

    settings = Settings()
    win = MainWindow(settings)

    QLocalServer.removeServer(SERVER)
    server = QLocalServer()
    server.listen(SERVER)
    pending = []
    flush = QTimer(singleShot=True, interval=250)

    def on_flush():
        got = pending[:]
        pending.clear()
        if got:
            win.open_paths(got)

    flush.timeout.connect(on_flush)

    def on_conn():
        while server.hasPendingConnections():
            c = server.nextPendingConnection()
            buf = bytearray()

            def read(c=c, buf=buf):
                buf.extend(bytes(c.readAll()))

            def done(c=c, buf=buf):
                read()
                try:
                    pending.extend(json.loads(buf.decode("utf-8")))
                except Exception:
                    pass
                flush.start()
                win.bring_to_front()
                c.deleteLater()

            c.readyRead.connect(read)
            c.disconnected.connect(done)
            read()
            if c.state() != QLocalSocket.ConnectedState:
                done()

    server.newConnection.connect(on_conn)

    win.show()
    if files:
        win.open_paths(files)
    if os.environ.get("YOUTOWN_SHOT") and not getattr(sys, "frozen", False):
        _dev_screenshot(app, win)
    return app.exec()


def _dev_screenshot(app, win):
    """Dev aid: YOUTOWN_SHOT=out.png [YOUTOWN_STEPS='python;...|python'] grabs the window after each step."""
    out = os.environ["YOUTOWN_SHOT"]
    steps = [s for s in os.environ.get("YOUTOWN_STEPS", "").split("|") if s.strip()] or ["pass"]
    delay = int(os.environ.get("YOUTOWN_DELAY", "3000"))

    def run(i=0):
        if i >= len(steps):
            win.quit_app()
            return
        try:
            exec(steps[i], {"win": win, "app": app})
        except Exception as ex:
            print("step error:", ex, flush=True)

        def grab():
            g = win.frameGeometry()
            pm = win.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height())
            pm.save(out.replace(".png", f"-{i}.png"))
            print("shot", i, flush=True)
            run(i + 1)

        QTimer.singleShot(delay, grab)

    QTimer.singleShot(int(os.environ.get("YOUTOWN_START", "2500")), run)
