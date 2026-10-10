"""Entry point: ``python -m fission360 [file.f3x]``."""
from __future__ import annotations

import os
import sys


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    # Prefer native Wayland/X11; fall back to xcb when Wayland lacks GL.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QSurfaceFormat
    from PySide6.QtWidgets import QApplication

    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName("Fission360")
    app.setOrganizationName("Fission360")
    app.setDesktopFileName("fission360")

    from PySide6.QtCore import QSettings
    from .ui import theme
    from .ui.icons import icon
    dark = QSettings("Fission360", "Fission360").value("theme", "light") == "dark"
    if dark:
        theme.apply_dark()
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET_DARK if dark else theme.STYLESHEET_LIGHT)
    app.setWindowIcon(icon("extrude"))

    from .ui.main_window import MainWindow
    win = MainWindow()
    if "--fullscreen" in argv:
        # remote/kiosk mode (no window manager): fill the virtual screen
        win.setGeometry(app.primaryScreen().geometry())
        win.showFullScreen()
    else:
        win.show()
    files = [a for a in argv[1:] if not a.startswith("-")]
    if files:
        win.open_doc(files[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
