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


def test_joint_command_and_component_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    from fission360.api import Design
    from fission360.core import kernel as K
    from fission360.ui.main_window import MainWindow
    from fission360.ui.viewport import Pick
    win = MainWindow()
    win.show()
    d = Design(win.doc)
    a = d.box(0, 0, 40, 30, 10)
    b = d.box(100, 0, 20, 20, 10)
    win.doc.set_component([b.body_id], "Lid")
    win.refresh_all()
    app.processEvents()
    ids = list(win.doc.state.bodies)

    def face(bid, nz):
        fs = K.faces(win.doc.state.bodies[bid].shape)
        return next(i for i, f in enumerate(fs) if abs(K.face_info(f)["normal"][2] - nz) < 1e-6)

    win.run("joint")
    win.viewport.set_selection([Pick("face", ids[1], face(ids[1], -1)), Pick("face", ids[0], face(ids[0], 1))])
    win.panel.update_preview()
    win.panel.accept()
    assert not [f.error for f in win.doc.features if f.error]
    lo, _ = K.bbox(win.doc.state.bodies[ids[1]].shape)
    assert abs(lo[2] - 10) < 1e-6
    names = [win.browser.topLevelItem(0).child(i).text(0) for i in range(win.browser.topLevelItem(0).childCount())]
    assert "Bodies (2)" in names
    win.doc.modified = False
    win.close()


def test_joint_motion_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    from fission360.api import Design
    from fission360.core import kernel as K
    from fission360.ui import dialogs as D
    from fission360.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    d = Design(win.doc)
    a = d.box(0, 0, 40, 30, 10)
    b = d.box(100, 0, 20, 20, 10)
    fa = a.faces(normal=(0, 0, 1))[0]
    fb = b.faces(normal=(0, 0, -1))[0]
    j = d.joint(fb, fa, kind="revolute", limits=(-90, 90))
    dlg = D.JointMotionDialog(win, j)
    dlg.slider.setValue(1000)             # maximum = +90 deg
    lo, hi = K.bbox(win.doc.state.bodies[b.body_id].shape)
    assert abs((hi - lo)[1] - 20) < 1e-3 and abs((hi - lo)[0] - 20) < 1e-3   # square block rotated 90 deg
    dlg._cancel()
    assert win.doc.val(win.doc.feature(j.id), "angle") == 0
    win.doc.modified = False
    win.close()


def test_flange_command_in_gui(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    from fission360.api import Design
    from fission360.core import kernel as K
    from fission360.ui.main_window import MainWindow
    from fission360.ui.viewport import Pick
    win = MainWindow()
    win.show()
    d = Design(win.doc)
    p = d.box(0, 0, 60, 40, 2)
    bid = p.body_id
    fs = K.faces(win.doc.state.bodies[bid].shape)
    idx = next(i for i, f in enumerate(fs) if K.face_info(f)["normal"][1] > 0.99)
    win.run("flange")
    win.viewport.set_selection([Pick("face", bid, idx)])
    win.panel.widgets["height"].setText("12 mm")
    win.panel.update_preview()
    win.panel.accept()
    assert not [f.error for f in win.doc.features if f.error]
    assert len(win.doc.state.sheet) == 1
    lo, hi = K.bbox(win.doc.state.bodies[bid].shape)
    assert hi[2] > 10
    win.doc.modified = False
    win.close()
