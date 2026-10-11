"""Browser tree and parametric timeline."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QMenu, QScrollArea, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.features import FEATURE_TYPES
from .icons import icon, pixmap
from .theme import THEME

ROLE = Qt.UserRole + 1


class Browser(QTreeWidget):
    """Fusion-style browser: origin, bodies, sketches, construction."""
    request = Signal(str, object)   # action, payload

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.header().resizeSection(1, 26)
        self.setIconSize(QSize(18, 18))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemClicked.connect(self._clicked)
        self.itemDoubleClicked.connect(self._double)
        self.itemChanged.connect(self._renamed)
        self.setEditTriggers(QTreeWidget.EditKeyPressed)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._expanded = {"root", "bodies", "sketches"}

    def refresh(self):
        doc = self.win.doc
        st = doc.state
        self.blockSignals(True)
        expanded = {self._key(it) for it in self._walk() if it.isExpanded()} or self._expanded
        self.clear()
        root = QTreeWidgetItem([doc.name + (" *" if doc.modified else "")])
        root.setIcon(0, icon("folder"))
        root.setData(0, ROLE, ("root", None))
        self.addTopLevelItem(root)

        def folder(name, key, ico="folder"):
            it = QTreeWidgetItem([name])
            it.setIcon(0, icon(ico))
            it.setData(0, ROLE, (key, None))
            root.addChild(it)
            return it

        origin = folder("Origin", "origin", "origin")
        vis = self.win.viewport.show_origin
        self._eye(origin, vis)
        for n in ("XY", "XZ", "YZ"):
            it = QTreeWidgetItem([f"{n} Plane"])
            it.setIcon(0, icon("plane"))
            it.setData(0, ROLE, ("origin_plane", n))
            origin.addChild(it)
        bodies = folder(f"Bodies ({len(st.bodies)})", "bodies", "folder")
        groups = {}
        for b in st.bodies.values():
            it = QTreeWidgetItem([doc.body_name(b.id)])
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            it.setIcon(0, icon("body"))
            it.setData(0, ROLE, ("body", b.id))
            self._eye(it, doc.body_visible(b.id))
            comp = doc.component_of(b.id)
            if comp and comp not in groups:
                g = QTreeWidgetItem([comp])
                g.setIcon(0, icon("folder"))
                g.setData(0, ROLE, ("component", comp))
                bodies.addChild(g)
                groups[comp] = g
            (groups[comp] if comp else bodies).addChild(it)
        sketches = [(f, st.sketches.get(f.id)) for f in doc.features if f.type == "sketch"]
        if sketches:
            sk_folder = folder(f"Sketches ({len(sketches)})", "sketches")
            for f, so in sketches:
                it = QTreeWidgetItem([f.name])
                it.setFlags(it.flags() | Qt.ItemIsEditable)
                it.setIcon(0, icon("sketch"))
                it.setData(0, ROLE, ("sketch", f.id))
                self._eye(it, doc.body_props.get(f.id, {}).get("visible", True))
                if f.error:
                    it.setIcon(0, icon("error"))
                    it.setToolTip(0, f.error)
                sk_folder.addChild(it)
        cons = [f for f in doc.features if f.type in ("plane_offset", "plane_angle", "axis_construct")]
        if cons:
            cf = folder("Construction", "construction")
            for f in cons:
                it = QTreeWidgetItem([f.name])
                it.setIcon(0, icon("plane" if f.type != "axis_construct" else "axis"))
                it.setData(0, ROLE, ("construct", f.id))
                self._eye(it, doc.body_props.get(f.id, {}).get("visible", True))
                cf.addChild(it)
        for it in self._walk():
            if self._key(it) in expanded or it is root:
                it.setExpanded(True)
        self.blockSignals(False)

    def _walk(self):
        out = []
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            out.append(it)
            stack.extend(it.child(i) for i in range(it.childCount()))
        return out

    @staticmethod
    def _key(it):
        d = it.data(0, ROLE)
        return d[0] if d and d[1] is None else (d[1] if d else None)

    def _eye(self, it, visible):
        it.setIcon(1, icon("eye" if visible else "eye_off"))
        it.setData(1, ROLE, visible)

    def _clicked(self, it, col):
        kind, key = it.data(0, ROLE)
        if col == 1 and it.data(1, ROLE) is not None:
            self.request.emit("toggle_visible", (kind, key))
            return
        if kind == "body":
            self.request.emit("select_body", key)

    def _renamed(self, it, col):
        kind, key = it.data(0, ROLE)
        name = it.text(0).strip()
        if not name or col != 0:
            return
        if kind == "body":
            self.request.emit("rename_body_to", (key, name))
        elif kind in ("sketch", "construct"):
            self.request.emit("rename_feature_to", (key, name))

    def _double(self, it, col):
        kind, key = it.data(0, ROLE)
        if kind == "sketch":
            self.request.emit("edit_sketch", key)
        elif kind == "construct":
            self.request.emit("edit_feature", key)
        elif kind == "body":
            self.editItem(it, 0)

    def _menu(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return
        kind, key = it.data(0, ROLE)
        m = QMenu(self)
        if kind == "body":
            m.addAction("Rename...", lambda: self.request.emit("rename_body", key))
            m.addAction(icon("appearance"), "Appearance...", lambda: self.request.emit("appearance", key))
            m.addAction("Physical Material...", lambda: self.request.emit("material", key))
            m.addAction("Set Component...", lambda: self.request.emit("set_component", key))
            m.addAction(icon("mass"), "Properties", lambda: self.request.emit("properties", key))
            m.addSeparator()
            m.addAction(icon("export"), "Export Body...", lambda: self.request.emit("export_body", key))
            m.addAction("Show/Hide", lambda: self.request.emit("toggle_visible", (kind, key)))
            m.addAction("Isolate", lambda: self.request.emit("isolate", key))
            m.addSeparator()
            m.addAction(icon("remove"), "Remove", lambda: self.request.emit("remove_body", key))
        elif kind == "sketch":
            m.addAction(icon("sketch"), "Edit Sketch", lambda: self.request.emit("edit_sketch", key))
            m.addAction("Show/Hide", lambda: self.request.emit("toggle_visible", (kind, key)))
            m.addAction("Rename...", lambda: self.request.emit("rename_feature", key))
            m.addAction(icon("remove"), "Delete", lambda: self.request.emit("delete_feature", key))
        elif kind == "construct":
            m.addAction("Edit Feature", lambda: self.request.emit("edit_feature", key))
            m.addAction("Show/Hide", lambda: self.request.emit("toggle_visible", (kind, key)))
            m.addAction(icon("remove"), "Delete", lambda: self.request.emit("delete_feature", key))
        elif kind == "origin_plane":
            m.addAction(icon("sketch"), "Create Sketch", lambda: self.request.emit("sketch_on", key))
        elif kind == "origin":
            m.addAction("Show/Hide", lambda: self.request.emit("toggle_visible", (kind, key)))
        elif kind == "bodies":
            m.addAction("Show All Bodies", lambda: self.request.emit("show_all", None))
        else:
            return
        m.exec(self.viewport().mapToGlobal(pos))


class Timeline(QWidget):
    """Horizontal parametric timeline with a draggable rollback marker."""
    request = Signal(str, object)
    CELL = 34

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("Timeline")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(2)
        for name, tip, act in (("play_first", "Move to beginning", "first"), ("play_prev", "Step back", "prev"),
                               ("play_next", "Step forward", "next"), ("play_last", "Move to end", "last")):
            b = QToolButton()
            b.setIcon(icon(name))
            b.setIconSize(QSize(14, 14))
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, a=act: self.request.emit("marker", a))
            lay.addWidget(b)
        self.strip = _Strip(self)
        sc = QScrollArea()
        sc.setWidget(self.strip)
        sc.setWidgetResizable(False)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setFixedHeight(self.CELL + 14)
        self.scroll = sc
        lay.addWidget(sc, 1)
        self.setFixedHeight(self.CELL + 20)

    def refresh(self):
        self.strip.refresh()


class _Strip(QWidget):
    def __init__(self, tl: Timeline):
        super().__init__()
        self.tl = tl
        self.setMouseTracking(True)
        self.hover = -1
        self.drag_marker = False
        self.drag_item = None
        self.selected = None
        self.refresh()

    @property
    def doc(self):
        return self.tl.win.doc

    def refresh(self):
        n = len(self.doc.features)
        self.setFixedSize(max(200, (n + 1) * Timeline.CELL + 20), Timeline.CELL + 10)
        self.update()

    def _cell(self, i):
        return QRect(6 + i * Timeline.CELL, 4, Timeline.CELL - 4, Timeline.CELL - 4)

    def _marker_x(self):
        return 6 + self.doc.marker * Timeline.CELL - 3

    def _index_at(self, x):
        i = int((x - 6) // Timeline.CELL)
        return i if 0 <= i < len(self.doc.features) else -1

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        doc = self.doc
        for i, f in enumerate(doc.features):
            r = self._cell(i)
            rolled = i >= doc.marker
            bg = QColor(255, 255, 255) if THEME.light else QColor(50, 53, 58)
            if i == self.hover:
                bg = QColor(215, 230, 251) if THEME.light else QColor(60, 80, 110)
            if f.id == self.selected:
                bg = QColor(185, 212, 248) if THEME.light else QColor(52, 80, 122)
            if f.error:
                bg = QColor(250, 210, 210)
            elif f.warning:
                bg = QColor(252, 236, 200)
            p.setPen(QPen(QColor(170, 176, 186), 1))
            p.setBrush(bg)
            p.drawRoundedRect(r, 4, 4)
            p.setOpacity(0.35 if rolled or f.suppressed else 1.0)
            ic = FEATURE_TYPES.get(f.type, {}).get("icon", "box")
            p.drawPixmap(r.adjusted(4, 4, -4, -4), pixmap(ic, 48))
            p.setOpacity(1.0)
            if f.suppressed:
                p.setPen(QPen(QColor(200, 60, 60), 2))
                p.drawLine(r.topLeft() + QPoint(3, 3), r.bottomRight() - QPoint(3, 3))
        # marker
        x = self._marker_x()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 100, 214))
        p.drawRoundedRect(QRect(x - 2, 1, 6, Timeline.CELL + 2), 2, 2)
        if self.drag_item is not None:
            tx = 6 + self.drag_item[1] * Timeline.CELL - 3
            p.setPen(QPen(QColor(230, 120, 30), 2, Qt.DashLine))
            p.drawLine(tx, 0, tx, self.height())

    def mousePressEvent(self, ev):
        x = ev.position().x()
        if abs(x - self._marker_x() - 1) < 7:
            self.drag_marker = True
            return
        i = self._index_at(x)
        if i < 0:
            return
        f = self.doc.features[i]
        self.selected = f.id
        if ev.button() == Qt.LeftButton:
            self.drag_item = [i, i, x]
        self.update()
        self.tl.request.emit("select", f.id)

    def mouseMoveEvent(self, ev):
        x = ev.position().x()
        if self.drag_marker:
            n = int(round((x - 6) / Timeline.CELL))
            n = max(0, min(n, len(self.doc.features)))
            if n != self.doc.marker:
                self.tl.request.emit("set_marker", n)
            self.update()
            return
        if self.drag_item is not None and abs(x - self.drag_item[2]) > 8:
            n = int(round((x - 6) / Timeline.CELL))
            self.drag_item[1] = max(0, min(n, len(self.doc.features)))
            self.update()
            return
        i = self._index_at(x)
        if i != self.hover:
            self.hover = i
            self.tl.request.emit("hover", self.doc.features[i].id if i >= 0 else None)
            if i >= 0:
                f = self.doc.features[i]
                tip = f.name + (f"\n⚠ {f.error}" if f.error else (f"\n{f.warning}" if f.warning else ""))
                if f.error_kind == "reference":
                    tip += "\nA face, edge or profile was lost - double-click to re-select it"
                self.setToolTip(tip)
            self.update()

    def mouseReleaseEvent(self, ev):
        if self.drag_marker:
            self.drag_marker = False
            return
        if self.drag_item is not None:
            i, target, _ = self.drag_item
            self.drag_item = None
            if target not in (i, i + 1):
                fid = self.doc.features[i].id
                self.tl.request.emit("move", (fid, target if target < i else target - 1))
            self.update()

    def mouseDoubleClickEvent(self, ev):
        i = self._index_at(ev.position().x())
        if i >= 0:
            self.tl.request.emit("edit_feature", self.doc.features[i].id)

    def contextMenuEvent(self, ev):
        i = self._index_at(ev.pos().x())
        if i < 0:
            return
        f = self.doc.features[i]
        m = QMenu(self)
        if f.error_kind == "reference":
            m.addAction(icon("warning"), "Repair lost references...", lambda: self.tl.request.emit("repair", f.id))
        m.addAction("Edit Feature" if f.type != "sketch" else "Edit Sketch",
                    lambda: self.tl.request.emit("edit_feature", f.id))
        if f.type == "joint":
            m.addAction(icon("joint"), "Joint Motion / Limits...", lambda: self.tl.request.emit("joint_motion", f.id))
        m.addAction("Rename...", lambda: self.tl.request.emit("rename_feature", f.id))
        m.addAction("Unsuppress Feature" if f.suppressed else "Suppress Feature",
                    lambda: self.tl.request.emit("suppress", f.id))
        m.addAction("Roll History Marker Here", lambda: self.tl.request.emit("set_marker", i + 1))
        m.addSeparator()
        m.addAction(icon("remove"), "Delete", lambda: self.tl.request.emit("delete_feature", f.id))
        m.exec(ev.globalPos())

    def leaveEvent(self, ev):
        self.hover = -1
        self.tl.request.emit("hover", None)
        self.update()
