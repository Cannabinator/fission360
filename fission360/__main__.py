"""Entry point: ``python -m fission360 [file.f3x]``."""
from __future__ import annotations

import os
import sys


def _headless(argv) -> int:
    """``fission360 --run script.py [design.f3x] [--out result.f3x]`` without a GUI."""
    from .api import Design, run_script
    i = argv.index("--run")
    if i + 1 >= len(argv):
        print("usage: fission360 --run script.py [design.f3x] [--out result.f3x]", file=sys.stderr)
        return 2
    script = argv[i + 1]
    rest = [a for a in argv[i + 2:] if not a.startswith("--")]
    design = Design.open(rest[0]) if rest and os.path.exists(rest[0]) else Design()
    try:
        run_script(script, design)
    except Exception as exc:  # report and fail the process, for CI use
        print(f"script failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if "--out" in argv:
        design.save(argv[argv.index("--out") + 1])
    failed = [f"{f.name}: {f.error}" for f in design.doc.features if f.error]
    for line in failed:
        print("feature error:", line, file=sys.stderr)
    return 1 if failed else 0


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if "--run" in argv:
        return _headless(argv)
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
