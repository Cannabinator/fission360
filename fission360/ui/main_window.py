"""Main application window."""
from __future__ import annotations

import base64
import os
import zlib

from PySide6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QColorDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..core import kernel as K
from ..core import references as R
from ..core.document import Document, Feature
from ..core.features import FEATURE_TYPES, encode_shape
from ..sketch.model import Sketch
from . import dialogs as D
from .feature_panel import FeaturePanel
from .icons import icon
from .panels import Browser, Timeline
from .sketch_session import SketchSession
from .viewport import Pick, Viewport

FILE_FILTER = "Fission360 Design (*.f3x);;All files (*)"
IMPORT_FILTER = "CAD files (*.step *.stp *.iges *.igs *.stl *.brep);;All files (*)"
EXPORT_FORMATS = ("STEP (*.step);;IGES (*.iges);;3MF for slicers (*.3mf);;STL mesh (*.stl);;OBJ mesh (*.obj);;"
                  "OCC BREP (*.brep)")


class Command:
    def __init__(self, key, label, ico, fn, shortcut="", mode="solid", tip=""):
        self.key, self.label, self.icon, self.fn = key, label, ico, fn
        self.shortcut, self.mode, self.tip = shortcut, mode, tip


class Ribbon(QWidget):
    """Tabbed toolbar with grouped big buttons (Fusion-style)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("Ribbon")
        self.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 0, 6, 2)
        v.setSpacing(0)
        self.tabbar = QWidget()
        self.tabbar.setObjectName("RibbonTabs")
        self.tab_lay = QHBoxLayout(self.tabbar)
        self.tab_lay.setContentsMargins(0, 0, 0, 0)
        self.tab_lay.setSpacing(0)
        v.addWidget(self.tabbar)
        self._tab_stretch_added = False
        self.body = QWidget()
        self.body_lay = QHBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 2, 0, 0)
        self.body_lay.setSpacing(4)
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidget(self.body)
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sc.setFixedHeight(108)
        v.addWidget(sc)
        self.tabs = {}
        self.tab_buttons = {}
        self.current = None
        self.tool_buttons = {}

    def add_tab(self, name, groups):
        """groups: list of (title, [cmd keys or ('menu', label, icon, [keys])])"""
        b = QPushButton(name)
        b.setCheckable(True)
        b.clicked.connect(lambda _=False, n=name: self.show_tab(n))
        self.tab_lay.insertWidget(len(self.tab_buttons), b)
        if not self._tab_stretch_added:
            self.tab_lay.addStretch(1)
            self._tab_stretch_added = True
        self.tab_buttons[name] = b
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        for title, items in groups:
            g = QWidget()
            gv = QVBoxLayout(g)
            gv.setContentsMargins(4, 0, 4, 0)
            gv.setSpacing(0)
            row = QHBoxLayout()
            row.setSpacing(1)
            for it in items:
                row.addWidget(self._button(it))
            gv.addLayout(row)
            lab = QLabel(title)
            lab.setObjectName("RibbonGroupLabel")
            lab.setAlignment(Qt.AlignCenter)
            gv.addWidget(lab)
            h.addWidget(g)
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet("color: #d4d8de;")
            h.addWidget(sep)
        h.addStretch(1)
        page.hide()
        self.body_lay.addWidget(page)
        self.tabs[name] = page

    def _button(self, it):
        w = self.win
        tb = QToolButton()
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tb.setIconSize(QSize(28, 28))
        tb.setAutoRaise(True)
        tb.setMinimumWidth(52)
        if isinstance(it, tuple) and it[0] == "menu":
            _, label, ico, keys = it
            tb.setText(label)
            tb.setMinimumWidth(max(52, tb.fontMetrics().horizontalAdvance(label) + 22))
            tb.setIcon(icon(ico))
            m = QMenu(tb)
            for k in keys:
                c = w.commands[k]
                a = m.addAction(icon(c.icon), c.label + (f"\t{c.shortcut}" if c.shortcut else ""))
                a.triggered.connect(lambda _=False, c=c: w.run(c.key))
            tb.setMenu(m)
            tb.setPopupMode(QToolButton.InstantPopup)
            return tb
        c = w.commands[it]
        text = c.label.replace(" ", "\n", 1) if len(c.label) > 10 else c.label
        tb.setText(text)
        fm = tb.fontMetrics()
        tb.setMinimumWidth(max(52, max(fm.horizontalAdvance(t) for t in text.split("\n")) + 14))
        tb.setIcon(icon(c.icon))
        tb.setToolTip(f"<b>{c.label}</b>" + (f" ({c.shortcut})" if c.shortcut else "") + (f"<br>{c.tip}" if c.tip else ""))
        tb.clicked.connect(lambda _=False, k=it: w.run(k))
        self.tool_buttons.setdefault(it, []).append(tb)
        return tb

    def show_tab(self, name):
        for n, page in self.tabs.items():
            page.setVisible(n == name)
            self.tab_buttons[n].setChecked(n == name)
        self.current = name

    def set_tab_visible(self, name, visible):
        self.tab_buttons[name].setVisible(visible)

    def set_checked(self, key, on):
        for tb in self.tool_buttons.get(key, []):
            tb.setCheckable(True)
            tb.setChecked(on)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Fission360", "Fission360")
        self.doc = Document()
        self.session: SketchSession | None = None
        self.panel = None
        self.last_command = None
        self.pending_sketch = False
        self.resize(1440, 900)

        self.viewport = Viewport()
        self.viewport.set_document(self.doc)
        self._build_commands()
        self.ribbon = Ribbon(self)
        self._build_ribbon()
        self.browser = Browser(self)
        self.browser.request.connect(self.on_request)
        self.timeline = Timeline(self)
        self.timeline.request.connect(self.on_request)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 0, 4)
        title = QLabel("  BROWSER")
        title.setStyleSheet("font-weight:600; color:#6b7380; padding:3px 0;")
        lv.addWidget(title)
        lv.addWidget(self.browser)
        split.addWidget(left)
        split.addWidget(self.viewport)
        split.setStretchFactor(1, 1)
        split.setSizes([250, 1190])
        central = QWidget()
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self.ribbon)
        cv.addWidget(split, 1)
        cv.addWidget(self.timeline)
        self.setCentralWidget(central)
        self._build_navbar()
        self._build_sketch_palette()
        self._build_menus()
        self._build_shortcuts()

        self.statusBar().showMessage("Ready")
        self.perf = QLabel("")
        self.statusBar().addPermanentWidget(self.perf)
        self.viewport.status.connect(lambda m: self.statusBar().showMessage(m, 3000))
        self.viewport.context_requested.connect(self.marking_menu)
        self.viewport.double_clicked.connect(self.on_viewport_double)
        self.viewport.selection_changed.connect(self.on_selection)
        self.viewport.hover_changed.connect(self.on_hover)
        self.attach_document(self.doc)
        self.ribbon.show_tab("SOLID")
        self.ribbon.set_tab_visible("SKETCH", False)

        self.autosave = QTimer(self)
        self.autosave.setInterval(120_000)
        self.autosave.timeout.connect(self.do_autosave)
        self.autosave.start()
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ------------------------------------------------------------------ commands
    def _build_commands(self):
        C = Command
        f = self.feature_command
        sk = self.sketch_tool
        cs = [
            C("new", "New Design", "new", self.new_doc, "Ctrl+N", "any"),
            C("open", "Open...", "open", self.open_doc, "Ctrl+O", "any"),
            C("save", "Save", "save", self.save_doc, "Ctrl+S", "any"),
            C("save_as", "Save As...", "save", self.save_doc_as, "Ctrl+Shift+S", "any"),
            C("import", "Import...", "import", self.import_file, "Ctrl+I", "solid", "STEP, IGES, STL or BREP"),
            C("export", "Export...", "export", self.export_file, "Ctrl+E", "any", "STEP, IGES, STL, OBJ or BREP"),
            C("undo", "Undo", "undo", self.undo, "Ctrl+Z", "any"),
            C("redo", "Redo", "redo", self.redo, "Ctrl+Y", "any"),
            C("create_sketch", "Create Sketch", "sketch", self.create_sketch, "", "solid",
              "Select a plane or planar face to sketch on"),
            C("parameters", "Change Parameters", "parameters", self.show_parameters, "", "any",
              "User & model parameters with expressions"),
            C("measure", "Measure", "measure", self.measure, "I", "any"),
            C("section", "Section Analysis", "section", self.section, "", "solid"),
            C("properties", "Properties", "mass", self.properties, "", "solid", "Mass, volume, center of mass"),
            C("interference", "Interference", "interference", lambda: D.interference_dialog(self), "", "solid"),
            C("finish_sketch", "Finish Sketch", "finish", self.finish_sketch, "", "sketch"),
            C("construction", "Construction", "construction", lambda: self.session and self.session.toggle_construction(), "X", "sketch",
              "Toggle selected curves between normal and construction geometry"),
            C("delete", "Delete", "remove", self.delete_selection, "Del", "any"),
            C("fit", "Fit", "fit", lambda: self.viewport.fit_selection(), "F6", "any",
              "Fit the selection, or everything when nothing is selected"),
            C("look_at", "Look At", "fit", self.look_at, "", "any", "Look straight at the selected face or plane"),
            C("press_pull", "Press Pull", "extrude", lambda: self.feature_command("extrude"), "Q", "solid",
              "Push/pull faces or profiles; joins or cuts automatically"),
            C("appearance", "Appearance", "appearance", self.appearance_selected, "A", "solid"),
            C("search", "Command Search", "search", self.command_search, "S", "any"),
        ]
        for ftype, spec in FEATURE_TYPES.items():
            if ftype in ("sketch", "import"):
                continue
            cs.append(C(ftype, spec["label"], spec["icon"], lambda t=ftype: f(t), spec.get("key", ""), "solid"))
        tools = [("ellipse", "Ellipse", "ellipse", ""), ("text", "Text", "text", ""),
                 ("extend", "Extend", "extend", "E"),
                 ("line", "Line", "line", "L"), ("rect", "2-Point Rectangle", "rect", "R"),
                 ("rect_center", "Center Rectangle", "rect_center", ""), ("circle", "Center Circle", "circle", "C"),
                 ("arc", "3-Point Arc", "arc", "A"), ("arc_center", "Center Point Arc", "arc_center", ""),
                 ("polygon", "Polygon", "polygon", ""), ("slot", "Slot", "slot", ""), ("spline", "Spline", "spline", ""),
                 ("point", "Point", "point", ""), ("dimension", "Sketch Dimension", "dimension", "D"),
                 ("trim", "Trim", "trim", "T"), ("sketch_fillet", "Sketch Fillet", "sketch_fillet", ""),
                 ("project", "Project", "project", "P")]
        for key, label, ico, sc in tools:
            cs.append(C("sk_" + key, label, ico, lambda k=key: sk(k), sc, "sketch"))
        ses = lambda name: (lambda: getattr(self.session, name)() if self.session else None)  # noqa: E731
        cs += [
            C("sk_offset", "Offset", "offset", ses("offset"), "O", "sketch", "Offset the selected curves"),
            C("sk_mirror", "Mirror", "mirror_sketch", ses("mirror"), "", "sketch",
              "Select curves, then the mirror line last"),
            C("sk_pattern_rect", "Rectangular Pattern", "pattern_rect", ses("pattern_rect"), "", "sketch"),
            C("sk_pattern_circ", "Circular Pattern", "pattern_circ", ses("pattern_circ"), "", "sketch"),
            C("sk_import_2d", "Insert DXF / SVG", "import2d", ses("import_2d"), "", "sketch",
              "Insert lines, arcs, circles and paths from a DXF or SVG file"),
            C("sk_export_dxf", "Export DXF", "dxf", ses("export_dxf"), "", "sketch"),
            C("drawing", "Export Drawing...", "dxf", self.export_drawing, "", "solid",
              "Orthographic views with hidden lines and overall dimensions, as SVG or DXF"),
            C("versions", "Version History", "save", self.show_versions, "", "any",
              "Save, compare and restore named versions"),
            C("run_script", "Run Script...", "parameters", self.run_script, "", "any",
              "Run a Python script against the open design"),
            C("select_other", "Select Other", "search", self.select_other, "", "solid",
              "Choose between overlapping faces under the cursor"),
        ]
        for kind in ("coincident", "horizontal", "vertical", "parallel", "perpendicular", "tangent", "equal",
                     "concentric", "midpoint", "collinear", "symmetric", "fix"):
            label = {"fix": "Fix/Unfix", "symmetric": "Symmetry"}.get(kind, kind.title())
            cs.append(C("c_" + kind, label, "c_" + kind,
                        lambda k=kind: self.session and self.session.apply_constraint(k), "", "sketch",
                        "Apply to the selected sketch geometry"))
        self.commands = {c.key: c for c in cs}

    def _build_ribbon(self):
        self.ribbon.add_tab("SOLID", [
            ("CREATE", ["create_sketch", "extrude", "revolve", "sweep", "loft", "hole", "rib",
                        ("menu", "Primitives", "box", ["box", "cylinder", "sphere", "torus", "coil"]),
                        ("menu", "Pattern", "pattern_rect", ["pattern_rect", "pattern_circ"]), "mirror"]),
            ("MODIFY", ["fillet", "chamfer", "shell", "draft", "thread", "combine", "move",
                        ("menu", "More", "scale", ["scale", "split_body", "remove"]), "parameters"]),
            ("CONSTRUCT", [("menu", "Plane", "plane", ["plane_offset", "plane_angle"]), "axis_construct"]),
            ("ASSEMBLE", ["joint"]),
            ("INSPECT", ["measure", "section", "properties", "interference"]),
            ("INSERT", ["import", "export", "drawing"]),
        ])
        self.ribbon.add_tab("SKETCH", [
            ("CREATE", ["sk_line", ("menu", "Rectangle", "rect", ["sk_rect", "sk_rect_center"]),
                        "sk_circle", ("menu", "Arc", "arc", ["sk_arc", "sk_arc_center"]),
                        "sk_ellipse", "sk_polygon", "sk_slot", "sk_spline", "sk_text", "sk_point", "sk_project"]),
            ("MODIFY", ["sk_offset", "sk_mirror", ("menu", "Pattern", "pattern_rect",
                                                   ["sk_pattern_rect", "sk_pattern_circ"]),
                        "sk_sketch_fillet", "sk_trim", "sk_extend", "construction"]),
            ("INSERT", ["sk_import_2d", "sk_export_dxf"]),
            ("CONSTRAINTS", ["sk_dimension", "c_coincident", "c_horizontal", "c_vertical", "c_parallel",
                             "c_perpendicular", "c_tangent", "c_equal",
                             ("menu", "More", "c_concentric", ["c_concentric", "c_midpoint", "c_collinear",
                                                               "c_symmetric", "c_fix"])]),
            ("", ["finish_sketch"]),
        ])

    def _build_navbar(self):
        nav = QFrame(self.viewport)
        nav.setObjectName("Panel")
        h = QHBoxLayout(nav)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(2)

        def btn(ico, tip, fn, checkable=False, checked=False):
            b = QToolButton()
            b.setIcon(icon(ico))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setChecked(checked)
            b.clicked.connect(fn)
            h.addWidget(b)
            return b

        btn("fit", "Fit (F6)", lambda: self.viewport.fit_all())
        self.ortho_btn = btn("zoom", "Orthographic / Perspective", self.toggle_ortho, True, False)
        disp = QToolButton()
        disp.setIcon(icon("display"))
        disp.setIconSize(QSize(20, 20))
        disp.setToolTip("Visual style")
        m = QMenu(disp)
        grp = QActionGroup(m)
        for key, label in (("shaded", "Shaded"), ("shaded_edges", "Shaded with Visible Edges"),
                           ("wireframe", "Wireframe")):
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == self.viewport.style)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_style(k))
        disp.setMenu(m)
        disp.setPopupMode(QToolButton.InstantPopup)
        h.addWidget(disp)
        btn("grid", "Toggle grid", self.toggle_grid, True, True)
        btn("origin", "Toggle origin", self.toggle_origin, True, False)
        self.navbar = nav
        nav.adjustSize()
        self.viewport.installEventFilter(self)

    def _build_sketch_palette(self):
        pal = QFrame(self.viewport)
        pal.setObjectName("Panel")
        v = QVBoxLayout(pal)
        v.setContentsMargins(0, 0, 0, 8)
        t = QLabel("SKETCH PALETTE")
        t.setObjectName("PanelTitle")
        v.addWidget(t)
        inner = QVBoxLayout()
        inner.setContentsMargins(10, 4, 10, 4)
        from PySide6.QtWidgets import QCheckBox
        self.cb_snap = QCheckBox("Snap to grid")
        self.cb_snap.toggled.connect(lambda on: setattr(self.session, "grid_snap", on) if self.session else None)
        self.cb_grid = QCheckBox("Sketch grid")
        self.cb_grid.setChecked(True)
        self.cb_grid.toggled.connect(lambda on: (setattr(self.viewport, "show_grid", on), self.viewport.update()))
        look = QPushButton(icon("fit"), " Look At")
        look.clicked.connect(lambda: self.session and self.viewport.look_at_frame(self.session.frame))
        self.dof_label = QLabel("")
        self.cb_dims = QCheckBox("Show dimensions")
        self.cb_dims.setChecked(True)
        self.cb_dims.toggled.connect(lambda on: (setattr(self.viewport, "show_dimensions", on), self.viewport.update()))
        self.cb_cons = QCheckBox("Show constraints")
        self.cb_cons.setChecked(True)
        self.cb_cons.toggled.connect(lambda on: (setattr(self.viewport, "show_constraints", on), self.viewport.update()))
        self.cb_prof = QCheckBox("Show profiles")
        self.cb_prof.setChecked(True)
        self.cb_prof.toggled.connect(lambda on: (setattr(self.viewport, "hide_profiles", not on), self.viewport.invalidate()))
        for w in (look, self.cb_grid, self.cb_snap, self.cb_dims, self.cb_cons, self.cb_prof, self.dof_label):
            inner.addWidget(w)
        v.addLayout(inner)
        fin = QPushButton(icon("finish"), " Finish Sketch")
        fin.setObjectName("Primary")
        fin.clicked.connect(self.finish_sketch)
        h = QHBoxLayout()
        h.setContentsMargins(10, 0, 10, 0)
        h.addWidget(fin)
        v.addLayout(h)
        pal.setFixedWidth(220)
        pal.adjustSize()
        pal.hide()
        self.palette_panel = pal

    def eventFilter(self, obj, ev):
        if obj is self.viewport and ev.type() == ev.Type.Resize:
            self._place_overlays()
        return super().eventFilter(obj, ev)

    def _place_overlays(self):
        vp = self.viewport
        self.navbar.adjustSize()
        self.navbar.move((vp.width() - self.navbar.width()) // 2, vp.height() - self.navbar.height() - 10)
        self.palette_panel.move(vp.width() - self.palette_panel.width() - 12, 150)
        if self.panel is not None:
            try:
                self.panel.place()
            except RuntimeError:
                self.panel = None

    def _build_menus(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        for k in ("new", "open", "save", "save_as"):
            self._menu_action(fm, k)
        self.recent_menu = fm.addMenu("Open Recent")
        self._refresh_recent()
        fm.addSeparator()
        self._menu_action(fm, "versions")
        self._menu_action(fm, "drawing")
        fm.addSeparator()
        self._menu_action(fm, "import")
        self._menu_action(fm, "export")
        fm.addSeparator()
        a = fm.addAction("Quit")
        a.setShortcut(QKeySequence.Quit)
        a.triggered.connect(self.close)
        em = mb.addMenu("&Edit")
        self.undo_action = self._menu_action(em, "undo")
        self.redo_action = self._menu_action(em, "redo")
        em.addSeparator()
        self._menu_action(em, "delete")
        self._menu_action(em, "parameters")
        em.addSeparator()
        self._menu_action(em, "search")
        vm = mb.addMenu("&View")
        for name in ("Home", "Front", "Back", "Top", "Bottom", "Left", "Right"):
            from .camera import STANDARD_VIEWS
            a = vm.addAction(name)
            a.triggered.connect(lambda _=False, n=name: self.viewport.animate_view(*STANDARD_VIEWS[n], fit=n == "Home"))
        vm.addSeparator()
        self._menu_action(vm, "fit")
        a = vm.addAction("Orthographic")
        a.setCheckable(True)
        a.triggered.connect(lambda on: self.toggle_ortho(on))
        a = vm.addAction("Dark Theme (restart)")
        a.setCheckable(True)
        a.setChecked(self.settings.value("theme", "light") == "dark")
        a.triggered.connect(lambda on: self.settings.setValue("theme", "dark" if on else "light"))
        im = mb.addMenu("&Inspect")
        for k in ("measure", "section", "properties", "interference"):
            self._menu_action(im, k)
        tm = mb.addMenu("&Tools")
        self._menu_action(tm, "run_script")
        self._menu_action(tm, "select_other")
        hm = mb.addMenu("&Help")
        hm.addAction("Keyboard && Mouse Shortcuts", self.show_shortcuts)
        hm.addAction("About Fission360", self.about)

    def _menu_action(self, menu, key):
        c = self.commands[key]
        a = menu.addAction(icon(c.icon), c.label)
        if c.shortcut and len(c.shortcut) > 1:
            a.setShortcut(QKeySequence(c.shortcut))
        a.triggered.connect(lambda _=False, k=key: self.run(k))
        return a

    def _build_shortcuts(self):
        # Single-key shortcuts are dispatched by mode (solid vs sketch).
        keys = {}
        for c in self.commands.values():
            if c.shortcut and len(c.shortcut) <= 3 and "+" not in c.shortcut:
                keys.setdefault(c.shortcut, []).append(c)
        for k, cmds in keys.items():
            sc = QShortcut(QKeySequence(k), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(lambda cmds=cmds: self._dispatch_key(cmds))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.escape)

    def _dispatch_key(self, cmds):
        mode = "sketch" if self.session else "solid"
        for c in cmds:
            if c.mode in (mode, "any"):
                self.run(c.key)
                return

    def run(self, key):
        c = self.commands[key]
        mode = "sketch" if self.session else "solid"
        if c.mode not in (mode, "any"):
            if mode == "sketch" and c.mode == "solid":
                self.finish_sketch()
            else:
                return
        if key not in ("undo", "redo", "search", "fit", "delete"):
            self.last_command = key
        c.fn()

    # ------------------------------------------------------------------ document
    def attach_document(self, doc):
        self.doc = doc
        doc.listeners.append(self.on_doc_event)
        self.viewport.set_document(doc)
        self.refresh_all()
        QTimer.singleShot(50, lambda: self.viewport.fit_all(animate=False))

    def on_doc_event(self, what):
        if what == "history" and self.session is not None:
            self.session.on_history()
        if what in ("rebuilt", "history", "display", "renamed", "saved"):
            QTimer.singleShot(0, self.refresh_all)

    def refresh_all(self):
        self.browser.refresh()
        self.timeline.refresh()
        self.viewport.invalidate()
        self._update_title()
        doc = self.doc
        self.undo_action.setEnabled(doc.can_undo())
        self.redo_action.setEnabled(doc.can_redo())
        self.undo_action.setText(f"Undo {doc.undo_label()}" if doc.can_undo() else "Undo")
        self.redo_action.setText(f"Redo {doc.redo_label()}" if doc.can_redo() else "Redo")
        failed = [f for f in doc.features if f.error]
        msg = f"Rebuild {doc.last_rebuild_ms:.0f} ms · {len(doc.state.bodies)} bodies"
        if failed:
            msg += f" · ⚠ {len(failed)} failing feature(s): " + ", ".join(f"{f.name} ({f.error})" for f in failed[:3])
        self.perf.setText(msg)

    def _update_title(self):
        self.setWindowTitle(f"{self.doc.name}{' *' if self.doc.modified else ''} — Fission360")

    def confirm_discard(self):
        if not self.doc.modified or not self.doc.features:
            return True
        r = QMessageBox.question(self, "Unsaved changes", f"Save changes to {self.doc.name}?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_doc()
        return r == QMessageBox.Discard

    def new_doc(self):
        if not self.confirm_discard():
            return
        self._end_modes()
        self.attach_document(Document())

    def open_doc(self, path=None):
        if not path:
            if not self.confirm_discard():
                return
            path, _ = QFileDialog.getOpenFileName(self, "Open Design", self._last_dir(), FILE_FILTER)
        if not path:
            return
        try:
            doc = Document.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open", f"Cannot open {path}:\n{exc}")
            return
        self._end_modes()
        self.attach_document(doc)
        self._add_recent(path)

    def save_doc(self):
        if not self.doc.path:
            return self.save_doc_as()
        try:
            self.doc.save(self.doc.path)
        except OSError as exc:
            QMessageBox.critical(self, "Save", str(exc))
            return False
        self.statusBar().showMessage(f"Saved {self.doc.path}", 4000)
        self._add_recent(self.doc.path)
        return True

    def save_doc_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Design", os.path.join(self._last_dir(), self.doc.name + ".f3x"),
                                              FILE_FILTER)
        if not path:
            return False
        if not path.endswith(".f3x"):
            path += ".f3x"
        self.doc.name = os.path.splitext(os.path.basename(path))[0]
        self.doc.path = path
        return self.save_doc()

    def _last_dir(self):
        return self.settings.value("last_dir", os.path.expanduser("~"))

    def _add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:10])
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent_menu.clear()
        for p in self.settings.value("recent", []) or []:
            self.recent_menu.addAction(p, lambda p=p: self.open_doc(p))

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import", self._last_dir(), IMPORT_FILTER)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            fn = {".step": K.import_step, ".stp": K.import_step, ".iges": K.import_iges, ".igs": K.import_iges,
                  ".stl": K.import_stl, ".brep": K.import_brep}[ext]
            shapes = fn(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import", f"Import failed:\n{exc}")
            return
        snap = self.doc.snapshot()
        f = Feature(self.doc.new_id(), "import", os.path.basename(path),
                    {"file": os.path.basename(path), "shapes": [encode_shape(s) for s in shapes]})
        self.doc.insert_feature(f)
        self.doc.push_undo("Import", snap)
        self.viewport.fit_all()

    def export_file(self, bids=None):
        path, flt = QFileDialog.getSaveFileName(self, "Export", os.path.join(self._last_dir(), self.doc.name + ".step"),
                                                EXPORT_FORMATS)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += "." + flt.split("*.")[1].rstrip(")")
        try:
            bodies = [self.doc.state.bodies[b] for b in bids] if bids else None
            self.doc.export_bodies(path, bodies)
            self.statusBar().showMessage(f"Exported {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Export", f"Export failed:\n{exc}")

    def do_autosave(self):
        if not self.doc.modified or not self.doc.features:
            return
        d = os.path.join(os.path.expanduser("~"), ".local", "share", "fission360", "autosave")
        try:
            os.makedirs(d, exist_ok=True)
            p, n, m = self.doc.path, self.doc.name, self.doc.modified
            self.doc.save(os.path.join(d, f"{n}.f3x"))
            self.doc.path, self.doc.name, self.doc.modified = p, n, m
            self._update_title()
        except OSError:
            pass

    # ------------------------------------------------------------------ undo
    def undo(self):
        if self.panel is not None:
            return
        self.doc.undo()

    def redo(self):
        if self.panel is not None:
            return
        self.doc.redo()

    # ------------------------------------------------------------------ modes
    def _end_modes(self):
        if self.panel is not None:
            try:
                self.panel.reject()
            except RuntimeError:
                pass
            self.panel = None
        if self.session is not None:
            self.finish_sketch()
        self._cancel_pending_sketch()

    def escape(self):
        if self.session is not None:
            if self.session.tool is not None and self.session.tool.name != "select":
                self.session.set_tool(None)
                return
            self.viewport.clear_selection()
            return
        if self.panel is not None:
            try:
                self.panel.reject()
            except RuntimeError:
                pass
            return
        if self.pending_sketch:
            self._cancel_pending_sketch()
            return
        self.viewport.clear_selection()

    def feature_command(self, ftype, feature=None):
        if self.session is not None:
            self.finish_sketch()
        if self.panel is not None:
            try:
                self.panel.reject()
            except RuntimeError:
                pass
        self._cancel_pending_sketch()
        pre = list(self.viewport.selection)
        self.viewport.clear_selection()
        self.panel = FeaturePanel(self, ftype, feature, preselect=pre)
        self.panel.finished.connect(self._panel_done)

    def _panel_done(self, ok):
        self.panel = None
        self.refresh_all()

    def edit_feature(self, fid):
        f = self.doc.feature(fid)
        if f is None:
            return
        if f.type == "sketch":
            self.edit_sketch(fid)
        elif f.type == "import":
            QMessageBox.information(self, "Import", "Imported bodies have no editable parameters.")
        else:
            self.feature_command(f.type, f)

    # ---- sketch mode
    def create_sketch(self):
        sel = self.viewport.selection
        target = None
        for p in sel:
            target = self._plane_ref_from_pick(p)
            if target:
                break
        if target is not None:
            self._start_sketch_on(target)
            return
        self.pending_sketch = True
        self.viewport.show_origin = True
        self.viewport.set_filter({"plane", "face"})
        self.viewport.clear_selection()
        self.viewport.selection_changed.connect(self._sketch_target_picked)
        self.viewport.invalidate()
        self.statusBar().showMessage("Select a plane or planar face to start a sketch")

    def _plane_ref_from_pick(self, p):
        if p.kind == "plane":
            return p.key if p.key in K.ORIGIN_FRAMES else {"plane": p.key}
        if p.kind == "face":
            body = self.doc.state.bodies.get(p.key)
            if body is None:
                return None
            face = K.faces(body.shape)[p.index]
            if K.face_info(face)["type"] != "plane":
                self.statusBar().showMessage("Sketches need a planar face", 4000)
                return None
            return {"face": R.face_ref(p.key, face)}
        return None

    def _sketch_target_picked(self):
        if not self.viewport.selection:
            return
        target = self._plane_ref_from_pick(self.viewport.selection[-1])
        if target is None:
            self.viewport.clear_selection()
            return
        self._cancel_pending_sketch()
        self._start_sketch_on(target)

    def _cancel_pending_sketch(self):
        if not self.pending_sketch:
            return
        self.pending_sketch = False
        try:
            self.viewport.selection_changed.disconnect(self._sketch_target_picked)
        except (RuntimeError, TypeError):
            pass
        self.viewport.show_origin = False
        self.viewport.set_filter(None)
        self.viewport.invalidate()

    def _start_sketch_on(self, plane_ref):
        snap = self.doc.snapshot()
        sk = Sketch()
        f = self.doc.add_feature("sketch", {"plane": plane_ref}, sketch=sk)
        f.sketch.param_value = self.doc.param_value
        self.doc.push_undo("Create Sketch", snap)
        self.edit_sketch(f.id, look=True)

    def edit_sketch(self, fid, look=True):
        if self.panel is not None:
            try:
                self.panel.reject()
            except RuntimeError:
                pass
        if self.session is not None:
            self.finish_sketch()
        self.doc.body_props.setdefault(fid, {})["visible"] = True
        self.session = SketchSession(self, fid)
        self.ribbon.set_tab_visible("SKETCH", True)
        self.ribbon.show_tab("SKETCH")
        self.palette_panel.show()
        self._place_overlays()
        if look:
            self.viewport.look_at_frame(self.session.frame)
        self.update_sketch_status()
        self.refresh_all()

    def finish_sketch(self, cancelled=False):
        if self.session is None:
            return
        s = self.session
        self.session = None
        s.finish()
        self.palette_panel.hide()
        self.ribbon.set_tab_visible("SKETCH", False)
        self.ribbon.show_tab("SOLID")
        self.viewport.set_filter(None)
        self.viewport.clear_selection()
        self.refresh_all()

    def sketch_tool(self, name):
        if self.session is None:
            return
        self.session.set_tool(name)

    def sketch_tool_changed(self, name):
        for k in self.commands:
            if k.startswith("sk_"):
                self.ribbon.set_checked(k, k == f"sk_{name}")

    def update_sketch_status(self):
        if self.session is None:
            return
        sk = self.session.sketch
        self.dof_label.setText("✔ Fully constrained" if sk.dof == 0 else f"{sk.dof} degrees of freedom")

    # ------------------------------------------------------------------ selection / actions
    def on_selection(self):
        sel = self.viewport.selection
        if not sel or self.panel is not None:
            return
        p = sel[-1]
        if p.kind in ("face", "edge", "vertex"):
            self.statusBar().showMessage(f"{p.kind.title()} of {self.doc.body_name(p.key)}", 3000)

    def on_hover(self, p):
        """Pre-selection feedback in the status bar (what a click would pick)."""
        if p is None:
            return
        names = {"face": "Face", "edge": "Edge", "vertex": "Vertex", "profile": "Profile", "curve": "Sketch curve",
                 "spoint": "Sketch point", "origin": "Sketch origin", "plane": "Plane"}
        what = names.get(p.kind, p.kind)
        if p.kind in ("face", "edge", "vertex") and p.key in self.doc.state.bodies:
            what += f" of {self.doc.body_name(p.key)}"
        elif p.kind in ("profile", "curve") and self.doc.feature(p.key):
            what += f" of {self.doc.feature(p.key).name}"
        self.statusBar().showMessage(what, 2000)

    def on_viewport_double(self, pick):
        if pick is None:
            return
        if pick.kind == "dimension" and self.session is not None:
            self.session.edit_dimension(pick.index, self.cursor().pos())
            return
        if self.session is not None:
            return
        if pick.kind in ("curve", "profile"):
            self.edit_sketch(pick.key)

    def delete_selection(self):
        if self.session is not None:
            self.session.delete_selection()
            return
        sel = self.viewport.selection
        bodies = sorted({p.key for p in sel if p.kind in ("face", "body", "edge")})
        tl_sel = self.timeline.strip.selected
        if bodies:
            snap = self.doc.snapshot()
            f = Feature(self.doc.new_id(), "remove", self.doc.default_name("remove"), {"bodies": bodies})
            self.doc.insert_feature(f)
            self.doc.push_undo("Remove body", snap)
            self.viewport.clear_selection()
        elif tl_sel and self.doc.feature(tl_sel):
            self.delete_feature(tl_sel)

    def delete_feature(self, fid):
        f = self.doc.feature(fid)
        if f is None:
            return
        snap = self.doc.snapshot()
        self.doc.delete_feature(fid)
        self.doc.push_undo(f"Delete {f.name}", snap)
        self.timeline.strip.selected = None

    def appearance_selected(self):
        bodies = sorted({p.key for p in self.viewport.selection if p.kind in ("face", "body")})
        if not bodies:
            bodies = list(self.doc.state.bodies)[:1]
        for b in bodies:
            self.on_request("appearance", b)

    def command_search(self):
        mode = "sketch" if self.session else "solid"
        cmds = [(c.label, c.icon, (lambda k=c.key: self.run(k)), c.shortcut) for c in self.commands.values()
                if c.mode in (mode, "any") or (mode == "sketch" and c.mode == "solid")]
        pop = D.CommandSearch(self, cmds)
        pos = self.viewport.mapToGlobal(QPoint(self.viewport.width() // 2 - 180, 80))
        pop.popup_at(pos)

    def marking_menu(self, gpos):
        if self.panel is not None:
            return
        C = self.commands

        def item(k):
            c = C[k]
            return (c.label, c.icon, lambda k=k: self.run(k))

        if self.session is not None:
            items = [item("finish_sketch"), item("sk_line"), item("sk_dimension"), item("sk_circle"),
                     item("delete"), item("sk_trim"), item("sk_rect"), item("construction")]
            over = [item(k) for k in ("undo", "redo", "c_horizontal", "c_vertical", "c_coincident", "c_fix")]
        else:
            rep = C.get(self.last_command) if self.last_command else None
            items = [(f"Repeat {rep.label}", rep.icon, lambda k=rep.key: self.run(k)) if rep else item("search"),
                     item("press_pull"), item("hole"), item("move"), item("delete"), item("fillet"),
                     item("create_sketch"), item("undo")]
            over = [item(k) for k in ("redo", "select_other", "look_at", "fit", "chamfer", "shell", "measure", "section", "properties", "appearance",
                                      "parameters")]
            sel_bodies = {p.key for p in self.viewport.selection if p.kind in ("face", "body")}
            if sel_bodies:
                over.insert(0, ("Edit feature that created body", "body",
                                lambda b=next(iter(sel_bodies)): self._edit_body_feature(b)))
        mm = D.MarkingMenu(self, items, over)
        mm.popup_at(gpos)

    def _edit_body_feature(self, bid):
        fid = bid.split(":")[0]
        if self.doc.feature(fid):
            self.edit_feature(fid)

    # ------------------------------------------------------------------ inspect
    def measure(self):
        if self.panel is not None or self.session is not None:
            return
        self.panel = D.InspectPanel(self)
        self.panel.closed.connect(lambda: setattr(self, "panel", None))

    def section(self):
        D.SectionPanel(self)

    def properties(self):
        bodies = sorted({p.key for p in self.viewport.selection if p.kind in ("face", "body", "edge")}) or \
            list(self.doc.state.bodies)
        D.properties_dialog(self, bodies)

    def export_drawing(self):
        from PySide6.QtWidgets import QFileDialog
        from .. import drawing
        bodies = self.doc.visible_bodies()
        if not bodies:
            self.statusBar().showMessage("Nothing to draw", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export drawing", f"{self.doc.name}.svg",
                                              "SVG drawing (*.svg);;DXF drawing (*.dxf)")
        if not path:
            return
        try:
            drawing.export_drawing(K.compound([b.shape for b in bodies]), path, self.doc.name,
                                   ("front", "top", "right", "iso"))
            self.statusBar().showMessage(f"Drawing saved to {path}", 5000)
        except Exception as exc:
            QMessageBox.warning(self, "Drawing", str(exc))

    def show_versions(self):
        if self.panel is not None or self.session is not None:
            return
        D.VersionsDialog(self).exec()
        self.refresh_all()

    def run_script(self):
        """Run a Python script against the open design (``design`` is bound to it)."""
        from PySide6.QtWidgets import QFileDialog
        from ..api import Design, run_script
        if self.panel is not None or self.session is not None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Run script", self._last_dir(), "Python (*.py);;All files (*)")
        if not path:
            return
        snap = self.doc.snapshot()
        try:
            run_script(path, Design(self.doc))
        except Exception as exc:  # report, keep whatever the script managed to build
            import traceback
            QMessageBox.warning(self, "Script error", "".join(traceback.format_exception_only(type(exc), exc)))
        self.doc.push_undo(f"Script {path.split('/')[-1]}", snap)
        self.refresh_all()
        self.viewport.fit_all()

    def select_other(self):
        """Clarify selection: choose between all faces along the ray under the cursor."""
        vp = self.viewport
        pos = vp.mapFromGlobal(self.cursor().pos())
        hits = vp.ray_faces(pos.x(), pos.y())
        if not hits:
            self.statusBar().showMessage("Nothing under the cursor", 3000)
            return
        menu = QMenu(self)
        for p, dist in hits:
            body = self.doc.body_name(p.key)
            a = menu.addAction(icon("body"), f"Face {p.index + 1} of {body}   ({dist:.1f} mm deep)")
            a.triggered.connect(lambda _=False, p=p: vp.set_selection([p]))
            a.hovered.connect(lambda p=p: (setattr(vp, "hover", p), vp.update()))
        menu.exec(self.cursor().pos())
        vp.hover = None
        vp.update()

    def show_parameters(self):
        D.ParametersDialog(self).exec()
        self.refresh_all()

    def show_shortcuts(self):
        from PySide6.QtWidgets import QDialog, QTextBrowser
        d = QDialog(self)
        d.setWindowTitle("Shortcuts")
        lay = QVBoxLayout(d)
        t = QTextBrowser()
        t.setHtml(D.SHORTCUTS)
        lay.addWidget(t)
        d.resize(460, 560)
        d.exec()

    def about(self):
        from OCP import __version__ as ocp_v  # noqa
        QMessageBox.about(self, "About Fission360",
                          f"<h3>Fission360 {__version__}</h3>Parametric 3D CAD for Linux.<br>"
                          "Kernel: OpenCASCADE (OCCT) via OCP · UI: Qt 6 · Rendering: OpenGL 3.3 core")

    # ------------------------------------------------------------------ view
    def toggle_ortho(self, on=None):
        self.viewport.cam.ortho = bool(on) if on is not None else not self.viewport.cam.ortho
        self.ortho_btn.setChecked(self.viewport.cam.ortho)
        self.viewport.pick_dirty = True
        self.viewport.update()

    def set_style(self, key):
        self.viewport.style = key
        self.viewport.update()

    def toggle_grid(self, on):
        self.viewport.show_grid = on
        self.viewport.update()

    def toggle_origin(self, on):
        self.viewport.show_origin = on
        self.viewport.invalidate()
        self.browser.refresh()

    # ------------------------------------------------------------------ browser / timeline requests
    def on_request(self, action, payload):
        doc = self.doc
        if action == "toggle_visible":
            kind, key = payload
            if kind == "origin":
                self.toggle_origin(not self.viewport.show_origin)
                return
            cur = doc.body_visible(key) if kind == "body" else doc.body_props.get(key, {}).get("visible", True)
            doc.set_body_prop(key, "visible", not cur)
        elif action == "select_body":
            self.viewport.set_selection([Pick("body", payload)])
        elif action == "edit_sketch":
            self.edit_sketch(payload)
        elif action == "edit_feature":
            self.edit_feature(payload)
        elif action == "delete_feature":
            self.delete_feature(payload)
        elif action == "rename_feature":
            f = doc.feature(payload)
            name, ok = QInputDialog.getText(self, "Rename", "Name:", text=f.name)
            if ok and name:
                snap = doc.snapshot()
                doc.rename_feature(payload, name)
                doc.push_undo("Rename", snap)
        elif action == "set_component":
            cur = doc.component_of(payload) or ""
            name, ok = QInputDialog.getText(self, "Component", "Component name (empty = none):", text=cur)
            if ok:
                targets = [payload]
                doc.set_component(targets, name.strip() or None)
        elif action == "rename_body":
            name, ok = QInputDialog.getText(self, "Rename Body", "Name:", text=doc.body_name(payload))
            if ok and name:
                doc.set_body_prop(payload, "name", name)
        elif action == "appearance":
            c = QColorDialog.getColor(QColor.fromRgbF(*doc.body_color(payload)), self, "Body Appearance",
                                      QColorDialog.ShowAlphaChannel)
            if c.isValid():
                doc.set_body_prop(payload, "color", [c.redF(), c.greenF(), c.blueF()])
                doc.set_body_prop(payload, "opacity", c.alphaF())
        elif action == "material":
            mats = list(D.MATERIALS)
            cur = doc.body_material(payload)
            m, ok = QInputDialog.getItem(self, "Physical Material", "Material:", mats,
                                         mats.index(cur) if cur in mats else 0, False)
            if ok:
                doc.set_body_prop(payload, "material", m)
        elif action == "properties":
            D.properties_dialog(self, [payload])
        elif action == "export_body":
            self.export_file([payload])
        elif action == "isolate":
            for b in doc.state.bodies:
                doc.body_props.setdefault(b, {})["visible"] = b == payload
            doc.notify("display")
        elif action == "show_all":
            for b in doc.state.bodies:
                doc.body_props.setdefault(b, {})["visible"] = True
            doc.notify("display")
        elif action == "remove_body":
            self.viewport.set_selection([Pick("body", payload)])
            self.delete_selection()
        elif action == "sketch_on":
            self._start_sketch_on(payload)
        elif action == "marker":
            n = {"first": 0, "prev": doc.marker - 1, "next": doc.marker + 1, "last": len(doc.features)}[payload]
            self._set_marker(n)
        elif action == "set_marker":
            self._set_marker(payload)
        elif action == "move":
            fid, idx = payload
            snap = doc.snapshot()
            doc.move_feature(fid, idx)
            doc.push_undo("Reorder", snap)
            bad = [f.name for f in doc.features if f.error]
            if bad:
                self.statusBar().showMessage("Reorder caused errors in: " + ", ".join(bad), 6000)
        elif action == "suppress":
            f = doc.feature(payload)
            snap = doc.snapshot()
            doc.set_suppressed(payload, not f.suppressed)
            doc.push_undo("Suppress" if f.suppressed else "Unsuppress", snap)
        elif action == "repair":
            self.edit_feature(payload)
        elif action == "hover":
            self.viewport.highlight_bodies = self.feature_bodies(payload) if payload else set()
            self.viewport.update()
        elif action == "rename_body_to":
            bid, name = payload
            if name != doc.body_name(bid):
                doc.set_body_prop(bid, "name", name)
        elif action == "rename_feature_to":
            fid, name = payload
            f = doc.feature(fid)
            if f and name != f.name:
                snap = doc.snapshot()
                doc.rename_feature(fid, name)
                doc.push_undo("Rename", snap)
        elif action == "select":
            pass

    def feature_bodies(self, fid):
        """Bodies created or modified by a feature (diff of timeline states)."""
        doc = self.doc
        try:
            i = doc.index_of(fid)
        except StopIteration:
            return set()
        after = doc._states[i] if i < len(doc._states) else None
        before = doc._states[i - 1] if i > 0 else None
        if after is None:
            return set()
        out = set()
        for bid, b in after.bodies.items():
            old = before.bodies.get(bid) if before else None
            if old is None or old.token != b.token:
                out.add(bid)
        return {b for b in out if b in self.viewport.vstate.bodies}

    def look_at(self):
        vp = self.viewport
        for p in reversed(vp.selection):
            ref = self._plane_ref_from_pick(p) if p.kind in ("face", "plane") else None
            if ref is None:
                continue
            fr = R.resolve_plane(vp.vstate, ref)
            vp.look_at_frame(fr)
            return
        if self.session is not None:
            vp.look_at_frame(self.session.frame)
            return
        self.statusBar().showMessage("Select a planar face or plane to look at", 4000)

    def _set_marker(self, n):
        if self.session is not None:
            self.finish_sketch()
        snap = self.doc.snapshot()
        self.doc.set_marker(n)
        self.doc.push_undo("Move history marker", snap)

    def closeEvent(self, ev):
        if not self.confirm_discard():
            ev.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        ev.accept()
