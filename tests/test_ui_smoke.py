"""Headless UI smoke test (needs an X display, e.g. xvfb-run)."""
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs an X display (run under xvfb-run)")


def test_window_sketch_extrude(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    from fission360.ui.main_window import MainWindow
    from fission360.ui.viewport import Pick
    win = MainWindow()
    win.show()
    app.processEvents()
    win._start_sketch_on("XY")
    sk = win.session.sketch
    sk.add_circle((0, 0), 10)
    win.session.changed("circle")
    win.finish_sketch()
    fid = win.doc.features[0].id
    win.run("extrude")
    win.viewport.set_selection([Pick("profile", fid, 0)])
    win.panel.widgets["distance"].setText("12 mm")
    win.panel.update_preview()
    win.panel.accept()
    assert len(win.doc.state.bodies) == 1
    img = win.viewport.grabFramebuffer()
    assert img.width() > 0
    win.doc.modified = False
    win.close()
