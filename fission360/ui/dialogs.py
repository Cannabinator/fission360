"""Dialogs & popups: parameters, command search, marking menu, inspect tools."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..core import kernel as K
from ..core.expressions import ExpressionError, format_angle, format_length, valid_param_name
from .icons import icon

MATERIALS = {"Steel": 7.85, "Stainless Steel": 8.0, "Aluminum 6061": 2.70, "Titanium": 4.43, "Copper": 8.96,
             "Brass": 8.5, "ABS Plastic": 1.04, "PLA Plastic": 1.24, "Nylon": 1.15, "Wood (Oak)": 0.75,
             "Glass": 2.5, "Concrete": 2.4}


# ---------------------------------------------------------------------------
class ParametersDialog(QDialog):
    """Fusion's 'Change Parameters': user + model parameters with expressions."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.doc = win.doc
        self.setWindowTitle("Parameters")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        add = QPushButton(icon("parameters"), " Add User Parameter")
        add.clicked.connect(self.add_param)
        bar.addWidget(add)
        rm = QPushButton("Delete")
        rm.clicked.connect(self.delete_param)
        bar.addWidget(rm)
        bar.addStretch(1)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter...")
        self.filter.textChanged.connect(self.populate)
        bar.addWidget(self.filter)
        lay.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Parameter", "Unit", "Expression", "Value", "Comment"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._changed)
        lay.addWidget(self.table)
        self.status = QLabel("")
        lay.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.populate()

    def _owner_name(self, p):
        if p.owner is None:
            return "User Parameters"
        f = self.doc.feature(p.owner)
        return f.name if f else p.owner

    def populate(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        flt = self.filter.text().lower()
        groups = [("User Parameters", self.doc.params.user_params())]
        by_owner = {}
        for p in self.doc.params.model_params():
            by_owner.setdefault(self._owner_name(p), []).append(p)
        groups += sorted(by_owner.items(), key=lambda kv: kv[0])
        for title, params in groups:
            params = [p for p in params if not flt or flt in p.name.lower() or flt in p.comment.lower()
                      or flt in title.lower()]
            if not params and title != "User Parameters":
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            it = QTableWidgetItem(title)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, it)
            self.table.setSpan(r, 0, 1, 5)
            for p in params:
                r = self.table.rowCount()
                self.table.insertRow(r)
                name = QTableWidgetItem(p.name)
                name.setData(Qt.UserRole, p.name)
                if p.owner is not None:
                    name.setFlags(name.flags() & ~Qt.ItemIsEditable)
                unit = QTableWidgetItem({"length": "mm", "angle": "deg", "scalar": ""}[p.kind])
                unit.setFlags(Qt.ItemIsEnabled)
                expr = QTableWidgetItem(p.expr)
                expr.setData(Qt.UserRole, p.name)
                try:
                    v = self.doc.params.value(p.name)
                    vs = format_length(v) if p.kind == "length" else format_angle(v) if p.kind == "angle" else f"{v:.6g}"
                except ExpressionError as exc:
                    vs = f"⚠ {exc}"
                val = QTableWidgetItem(vs)
                val.setFlags(Qt.ItemIsEnabled)
                com = QTableWidgetItem(p.comment)
                com.setData(Qt.UserRole, p.name)
                for c, item in enumerate((name, unit, expr, val, com)):
                    self.table.setItem(r, c, item)
        self.table.resizeColumnToContents(0)
        self.table.blockSignals(False)

    def _changed(self, item):
        pname = item.data(Qt.UserRole)
        if pname is None:
            return
        col = item.column()
        doc = self.doc
        snap = doc.snapshot()
        try:
            if col == 2:
                doc.params.set_expr(pname, item.text())
                label = f"Change {pname}"
            elif col == 0:
                new = item.text().strip()
                if new == pname:
                    return
                doc.params.rename(pname, new)
                label = f"Rename {pname}"
            elif col == 4:
                doc.params.params[pname].comment = item.text()
                label = "Edit comment"
            else:
                return
            doc.rebuild()
            doc.push_undo(label, snap)
            failed = [f.name for f in doc.features if f.error]
            self.status.setText(f"⚠ Failing features: {', '.join(failed)}" if failed else
                                f"Model updated in {doc.last_rebuild_ms:.0f} ms")
        except ExpressionError as exc:
            self.status.setText(f"⚠ {exc}")
        QTimer.singleShot(0, self.populate)

    def add_param(self):
        d = QDialog(self)
        d.setWindowTitle("Add User Parameter")
        f = QFormLayout(d)
        name = QLineEdit()
        kind = QComboBox()
        kind.addItems(["length", "angle", "scalar"])
        expr = QLineEdit("10 mm")
        com = QLineEdit()
        f.addRow("Name", name)
        f.addRow("Unit", kind)
        f.addRow("Expression", expr)
        f.addRow("Comment", com)
        kind.currentTextChanged.connect(lambda k: expr.setText({"length": "10 mm", "angle": "30 deg", "scalar": "1"}[k]))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        snap = self.doc.snapshot()
        try:
            if not valid_param_name(name.text()):
                raise ExpressionError("Invalid name (letters, digits, underscore; must not start with a digit)")
            self.doc.params.add(expr.text(), kind.currentText(), None, name.text(), com.text())
            self.doc.push_undo("Add parameter", snap)
        except ExpressionError as exc:
            QMessageBox.warning(self, "Parameter", str(exc))
        self.populate()

    def delete_param(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        snap = self.doc.snapshot()
        for r in rows:
            it = self.table.item(r, 0)
            pname = it.data(Qt.UserRole) if it else None
            if pname and self.doc.params.params[pname].owner is None:
                try:
                    self.doc.params.remove(pname)
                except ExpressionError as exc:
                    QMessageBox.warning(self, "Parameter", str(exc))
                    return
        self.doc.push_undo("Delete parameter", snap)
        self.doc.rebuild()
        self.populate()


# ---------------------------------------------------------------------------
class CommandSearch(QFrame):
    """Press S: fuzzy command search (Fusion's toolbox)."""

    def __init__(self, win, commands):
        super().__init__(win, Qt.Popup)
        self.setObjectName("Panel")
        self.commands = commands  # list of (label, icon, callback, shortcut)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search commands...")
        self.list = QListWidget()
        lay.addWidget(self.edit)
        lay.addWidget(self.list)
        self.edit.textChanged.connect(self.populate)
        self.edit.returnPressed.connect(self.run)
        self.list.itemActivated.connect(lambda _: self.run())
        self.resize(360, 380)
        self.populate("")

    @staticmethod
    def score(q, label):
        q, l = q.lower(), label.lower()
        if not q:
            return 1
        if l.startswith(q):
            return 100 - len(l)
        if q in l:
            return 50 - l.index(q)
        i = 0
        for ch in l:
            if i < len(q) and ch == q[i]:
                i += 1
        return 10 if i == len(q) else 0

    def populate(self, text=None):
        q = self.edit.text()
        self.list.clear()
        ranked = sorted(((self.score(q, c[0]), c) for c in self.commands), key=lambda t: -t[0])
        for s, c in ranked:
            if s <= 0:
                continue
            it = QListWidgetItem(icon(c[1]), c[0] + (f"   ({c[3]})" if c[3] else ""))
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Down, Qt.Key_Up):
            self.list.keyPressEvent(ev)
            return
        super().keyPressEvent(ev)

    def run(self):
        it = self.list.currentItem()
        self.close()
        if it is not None:
            it.data(Qt.UserRole)[2]()

    def popup_at(self, pos):
        self.move(pos)
        self.show()
        self.edit.setFocus()


# ---------------------------------------------------------------------------
class MarkingMenu(QWidget):
    """Radial right-click menu (8 slots) with an overflow list below."""

    def __init__(self, parent, items, overflow=()):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.items = items[:8]          # (label, icon, callback)
        self.overflow = list(overflow)
        self.R = 105
        self.hover = None
        n_over = len(self.overflow)
        self.resize(2 * self.R + 200, 2 * self.R + 80 + n_over * 24)
        self.center = QPointF(self.width() / 2, self.R + 40)

    def popup_at(self, gpos):
        self.move(gpos.x() - int(self.center.x()), gpos.y() - int(self.center.y()))
        self.show()

    def _slot_rect(self, i):
        ang = -math.pi / 2 + i * 2 * math.pi / 8
        c = self.center + QPointF(math.cos(ang) * self.R, math.sin(ang) * self.R * 0.85)
        return QRectF(c.x() - 62, c.y() - 13, 124, 26)

    def _over_rect(self, i):
        return QRectF(self.center.x() - 90, self.center.y() + self.R + 22 + i * 24, 180, 22)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(120, 125, 135, 150), 1))
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawEllipse(self.center, 16, 16)
        f = QFont(self.font())
        f.setPointSizeF(9)
        p.setFont(f)
        for i, (label, ic, _) in enumerate(self.items):
            r = self._slot_rect(i)
            hov = self.hover == ("s", i)
            p.setPen(QPen(QColor(150, 155, 165), 1))
            p.setBrush(QColor(10, 100, 214) if hov else QColor(250, 250, 252, 240))
            p.drawRoundedRect(r, 12, 12)
            icon(ic).paint(p, int(r.left() + 6), int(r.top() + 4), 18, 18)
            p.setPen(QColor(255, 255, 255) if hov else QColor(30, 34, 40))
            p.drawText(r.adjusted(28, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
        if self.overflow:
            box = QRectF(self.center.x() - 94, self.center.y() + self.R + 18, 188, len(self.overflow) * 24 + 8)
            p.setPen(QPen(QColor(150, 155, 165), 1))
            p.setBrush(QColor(250, 250, 252, 245))
            p.drawRoundedRect(box, 6, 6)
            for i, (label, ic, _) in enumerate(self.overflow):
                r = self._over_rect(i)
                if self.hover == ("o", i):
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(215, 230, 251))
                    p.drawRoundedRect(r, 4, 4)
                icon(ic).paint(p, int(r.left() + 4), int(r.top() + 2), 18, 18)
                p.setPen(QColor(30, 34, 40))
                p.drawText(r.adjusted(28, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    def _hit(self, pos):
        for i in range(len(self.items)):
            if self._slot_rect(i).contains(pos):
                return ("s", i)
        for i in range(len(self.overflow)):
            if self._over_rect(i).contains(pos):
                return ("o", i)
        # gesture: direction from centre selects the slot
        d = pos - self.center
        if math.hypot(d.x(), d.y()) > 40 and math.hypot(d.x(), d.y()) < self.R + 60:
            ang = math.atan2(d.y() / 0.85, d.x()) + math.pi / 2
            i = int(round(ang / (2 * math.pi / 8))) % 8
            if i < len(self.items):
                return ("s", i)
        return None

    def mouseMoveEvent(self, ev):
        h = self._hit(ev.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def mouseReleaseEvent(self, ev):
        h = self._hit(ev.position())
        if h is None:
            if ev.button() == Qt.LeftButton:
                self.close()
            return
        self.close()
        lst = self.items if h[0] == "s" else self.overflow
        QTimer.singleShot(0, lst[h[1]][2])


# ---------------------------------------------------------------------------
class InspectPanel(QFrame):
    """Measure tool: select up to two entities, report distance/angle/size."""
    closed = Signal()

    def __init__(self, win):
        super().__init__(win.viewport)
        self.setObjectName("Panel")
        self.win = win
        self.vp = win.viewport
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        t = QLabel("MEASURE")
        t.setObjectName("PanelTitle")
        lay.addWidget(t)
        self.out = QTextBrowser()
        self.out.setMinimumHeight(170)
        self.out.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.out)
        h = QHBoxLayout()
        h.setContentsMargins(10, 0, 10, 0)
        h.addStretch(1)
        b = QPushButton("Close")
        b.clicked.connect(self.close_panel)
        h.addWidget(b)
        lay.addLayout(h)
        self.setFixedWidth(320)
        self.vp.set_filter({"face", "edge", "vertex"})
        self.vp.clear_selection()
        self.vp.selection_changed.connect(self.update_measure)
        self.update_measure()
        self.adjustSize()
        self.move(self.vp.width() - self.width() - 12, 140)
        self.show()

    def _shape(self, p):
        b = self.vp.vstate.bodies.get(p.key)
        if b is None:
            return None
        if p.kind == "face":
            return K.faces(b.shape)[p.index]
        if p.kind == "edge":
            return K.edges(b.shape)[p.index]
        if p.kind == "vertex":
            return K.vertices(b.shape)[p.index]
        return None

    def update_measure(self):
        sel = self.vp.selection[-2:]
        if len(self.vp.selection) > 2:
            self.vp.selection = sel
        lines = []
        self.vp.labels = []
        try:
            shapes = [self._shape(p) for p in sel]
            for p, s in zip(sel, shapes):
                if p.kind == "face":
                    info = K.face_info(s)
                    lines.append(f"<b>Face</b> ({info['type']}): area {info['area']:.4g} mm²")
                    if "radius" in info:
                        lines.append(f"&nbsp;&nbsp;radius {format_length(info['radius'])}")
                elif p.kind == "edge":
                    info = K.edge_info(s)
                    lines.append(f"<b>Edge</b> ({info['type']}): length {format_length(info['length'])}")
                    if "radius" in info:
                        lines.append(f"&nbsp;&nbsp;radius {format_length(info['radius'])}")
                elif p.kind == "vertex":
                    v = K.vertex_point(s)
                    lines.append(f"<b>Point</b>: ({v[0]:.4g}, {v[1]:.4g}, {v[2]:.4g})")
            if len(shapes) == 2:
                d, pa, pb = K.distance(shapes[0], shapes[1])
                lines.append(f"<br><b>Minimum distance: {format_length(d)}</b>")
                dv = pb - pa
                lines.append(f"&nbsp;&nbsp;ΔX {dv[0]:.4g}, ΔY {dv[1]:.4g}, ΔZ {dv[2]:.4g}")
                self.vp.labels = [((pa + pb) / 2, format_length(d), (0.05, 0.45, 0.95))]
                dirs = []
                for p, s in zip(sel, shapes):
                    if p.kind == "face":
                        fi = K.face_info(s)
                        if fi["type"] == "plane":
                            dirs.append(np.array(fi["normal"]))
                    elif p.kind == "edge":
                        ei = K.edge_info(s)
                        if ei["type"] == "line":
                            dirs.append(np.array(ei["tangent"]))
                if len(dirs) == 2:
                    a = math.degrees(math.acos(max(-1, min(1, abs(float(np.dot(dirs[0], dirs[1])))))))
                    lines.append(f"<b>Angle:</b> {a:.3f}°")
        except Exception as exc:
            lines.append(f"⚠ {exc}")
        if not sel:
            lines = ["Select faces, edges or vertices (up to two)."]
        self.out.setHtml("<br>".join(lines))
        self.vp.update()

    def close_panel(self):
        try:
            self.vp.selection_changed.disconnect(self.update_measure)
        except (RuntimeError, TypeError):
            pass
        self.vp.labels = []
        self.vp.set_filter(None)
        self.vp.clear_selection()
        self.hide()
        self.deleteLater()
        self.closed.emit()


class SectionPanel(QFrame):
    """Section analysis: clip the view with a plane."""

    def __init__(self, win):
        super().__init__(win.viewport)
        self.setObjectName("Panel")
        self.win = win
        self.vp = win.viewport
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        t = QLabel("SECTION ANALYSIS")
        t.setObjectName("PanelTitle")
        lay.addWidget(t)
        form = QFormLayout()
        form.setContentsMargins(10, 4, 10, 4)
        self.plane = QComboBox()
        for n in ("XY", "XZ", "YZ"):
            self.plane.addItem(f"{n} Plane", n)
        self.flip = QComboBox()
        self.flip.addItems(["Normal", "Flipped"])
        self.off = QDoubleSpinBox()
        self.off.setRange(-1e5, 1e5)
        self.off.setDecimals(3)
        self.off.setSuffix(" mm")
        lo, hi = win.viewport.scene_bounds()
        self.off.setSingleStep(max(float(np.max(hi - lo)) / 50, 0.1))
        form.addRow("Plane", self.plane)
        form.addRow("Offset", self.off)
        form.addRow("Side", self.flip)
        lay.addLayout(form)
        h = QHBoxLayout()
        h.setContentsMargins(10, 0, 10, 0)
        h.addStretch(1)
        ok = QPushButton("OK")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.close_keep)
        rm = QPushButton("Remove")
        rm.clicked.connect(self.close_remove)
        h.addWidget(ok)
        h.addWidget(rm)
        lay.addLayout(h)
        for w in (self.plane, self.flip):
            w.currentIndexChanged.connect(self.apply)
        self.off.valueChanged.connect(self.apply)
        self.setFixedWidth(300)
        self.adjustSize()
        self.move(self.vp.width() - self.width() - 12, 140)
        self.apply()
        self.show()

    def apply(self):
        fr = K.ORIGIN_FRAMES[self.plane.currentData()]
        n = fr.normal * (-1 if self.flip.currentIndex() else 1)
        self.vp.section = (fr.origin + fr.normal * self.off.value(), n)
        self.vp.pick_dirty = True
        self.vp.update()

    def close_keep(self):
        self.hide()
        self.deleteLater()

    def close_remove(self):
        self.vp.section = None
        self.vp.update()
        self.close_keep()


def properties_dialog(win, bids):
    doc = win.doc
    rows = []
    tot_m = tot_v = 0.0
    for bid in bids:
        b = doc.state.bodies.get(bid)
        if b is None:
            continue
        mat = doc.body_material(bid)
        mp = K.mass_properties(b.shape, MATERIALS.get(mat, 7.85))
        tot_m += mp["mass_g"]
        tot_v += mp["volume_mm3"]
        c = mp["center_of_mass"]
        lo, hi = np.array(mp["bbox_min"]), np.array(mp["bbox_max"])
        sz = hi - lo
        rows.append(f"<h3>{doc.body_name(bid)}</h3><table>"
                    f"<tr><td>Material</td><td>{mat}</td></tr>"
                    f"<tr><td>Mass</td><td>{mp['mass_g']:.4g} g</td></tr>"
                    f"<tr><td>Volume</td><td>{mp['volume_mm3']:.6g} mm³</td></tr>"
                    f"<tr><td>Area</td><td>{mp['area_mm2']:.6g} mm²</td></tr>"
                    f"<tr><td>Center of mass</td><td>({c[0]:.4g}, {c[1]:.4g}, {c[2]:.4g}) mm</td></tr>"
                    f"<tr><td>Bounding box</td><td>{sz[0]:.4g} × {sz[1]:.4g} × {sz[2]:.4g} mm</td></tr></table>")
    if len(rows) > 1:
        rows.append(f"<h3>Total</h3>Mass {tot_m:.4g} g, volume {tot_v:.6g} mm³")
    d = QDialog(win)
    d.setWindowTitle("Properties")
    lay = QVBoxLayout(d)
    t = QTextBrowser()
    t.setHtml("".join(rows) or "No bodies")
    lay.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.Close)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    d.resize(420, 380)
    d.exec()


def interference_dialog(win):
    doc = win.doc
    bodies = list(doc.visible_bodies())
    hits = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            try:
                c = K.common(bodies[i].shape, bodies[j].shape)
                v = K.mass_properties(c)["volume_mm3"] if K.solids(c) else 0.0
            except Exception:
                v = 0.0
            if v > 1e-6:
                hits.append(f"{doc.body_name(bodies[i].id)} ∩ {doc.body_name(bodies[j].id)}: {v:.4g} mm³")
    QMessageBox.information(win, "Interference", "\n".join(hits) if hits else "No interference between visible bodies.")


SHORTCUTS = """
<h3>Navigation</h3>
<table>
<tr><td>Orbit</td><td>Shift + Middle drag, Right drag, or Alt + Left drag</td></tr>
<tr><td>Pan</td><td>Middle drag</td></tr>
<tr><td>Zoom</td><td>Mouse wheel (zooms about the cursor)</td></tr>
<tr><td>Fit all</td><td>F6 or double-click middle button</td></tr>
<tr><td>Standard views</td><td>Click a ViewCube face; Home button for isometric</td></tr>
</table>
<h3>Commands</h3>
<table>
<tr><td>S</td><td>Command search</td></tr>
<tr><td>Right click</td><td>Marking menu</td></tr>
<tr><td>E</td><td>Extrude</td></tr><tr><td>F</td><td>Fillet</td></tr><tr><td>H</td><td>Hole</td></tr>
<tr><td>M</td><td>Move/Copy</td></tr><tr><td>I</td><td>Measure</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>Undo / Redo</td></tr><tr><td>Del</td><td>Delete selection</td></tr>
</table>
<h3>Sketch</h3>
<table>
<tr><td>L</td><td>Line</td></tr><tr><td>R</td><td>2-point rectangle</td></tr><tr><td>C</td><td>Center circle</td></tr>
<tr><td>A</td><td>3-point arc</td></tr><tr><td>P</td><td>Project</td></tr><tr><td>T</td><td>Trim</td></tr>
<tr><td>D</td><td>Dimension</td></tr><tr><td>X</td><td>Toggle construction</td></tr>
<tr><td>Esc</td><td>Cancel current tool</td></tr><tr><td>Enter</td><td>Finish spline</td></tr>
</table>
"""
