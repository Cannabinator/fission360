"""Command panel: dialog for creating/editing a feature with live preview.

The panel is generated from the declarative spec in ``core.features``.  While
it is open the viewport shows the model *before* the feature (so original
geometry stays selectable) and the would-be result as a preview overlay,
recomputed (debounced) whenever an input changes.
"""
from __future__ import annotations

import copy

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..core import kernel as K
from ..core import references as R
from ..core.document import Feature
from ..core.expressions import ExpressionError
from ..core.features import (DIRECTION_LABELS, FEATURE_TYPES, NUMERIC_KINDS, OP_LABELS, default_data,
                             execute)
from .icons import icon
from .viewport import Pick

SELECT_KINDS = {
    "profiles": {"profile", "face"},
    "edges": {"edge", "face"},
    "faces": {"face"},
    "bodies": {"face"},
    "body": {"face"},
    "points": {"spoint"},
    "path": {"curve"},
    "plane": {"plane", "face"},
    "axis": {"curve", "edge", "face"},
}
MULTI = {"profiles", "edges", "faces", "bodies", "points", "path"}


_NUM_RE = __import__("re").compile(r"^\s*(-?\d+(?:\.\d*)?|-?\.\d+)\s*([a-z]*)\s*$")


class ExprEdit(QLineEdit):
    """Value field: expressions, Up/Down/wheel stepping, evaluated tooltip.

    Up/Down step by 1 (Shift: 0.1, Ctrl: 10) when the field holds a plain
    number with an optional unit, like Fusion's value boxes.
    """
    stepped = Signal()

    def __init__(self, text, kind, evaluate):
        super().__init__(text)
        self.kind = kind
        self.evaluate = evaluate
        self.textChanged.connect(self._tip)
        self._tip()

    def _tip(self):
        try:
            v = self.evaluate(self.text(), self.kind)
            from ..core.expressions import format_angle, format_length
            txt = format_length(v) if self.kind == "length" else format_angle(v) if self.kind == "angle" else f"{v:g}"
            self.setToolTip(f"= {txt}<br><i>Up/Down or wheel to step (Shift ×0.1, Ctrl ×10)</i>")
        except Exception as exc:
            self.setToolTip(str(exc))

    def step(self, n, mods):
        m = _NUM_RE.match(self.text())
        if not m:
            return
        k = 0.1 if mods & Qt.ShiftModifier else 10.0 if mods & Qt.ControlModifier else 1.0
        if self.kind == "scalar" and k < 1:
            k = 1.0
        v = float(m.group(1)) + n * k
        if self.kind == "scalar":
            v = max(1.0, v) if float(m.group(1)) >= 1 else v
        txt = f"{v:.4f}".rstrip("0").rstrip(".")
        unit = m.group(2) or {"length": "mm", "angle": "deg", "scalar": ""}[self.kind]
        self.setText(f"{txt} {unit}".strip())
        self.stepped.emit()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Up, Qt.Key_Down):
            self.step(1 if ev.key() == Qt.Key_Up else -1, ev.modifiers())
            return
        super().keyPressEvent(ev)

    def wheelEvent(self, ev):
        if self.hasFocus():
            self.step(1 if ev.angleDelta().y() > 0 else -1, ev.modifiers())
            ev.accept()
            return
        super().wheelEvent(ev)


class FeaturePanel(QFrame):
    finished = Signal(bool)

    def __init__(self, win, ftype: str, feature: Feature | None = None, preselect=None):
        super().__init__(win.viewport)
        self.setObjectName("Panel")
        self.win = win
        self.doc = win.doc
        self.vp = win.viewport
        self.ftype = ftype
        self.spec = FEATURE_TYPES[ftype]
        self.editing = feature is not None
        self.snapshot = self.doc.snapshot()
        if feature is None:
            fid = self.doc.new_id()
            self.f = Feature(fid, ftype, self.doc.default_name(ftype), default_data(ftype))
            for fs in self.spec["fields"]:
                if fs["kind"] in NUMERIC_KINDS:
                    self.f.params[fs["key"]] = self.doc.params.add(fs["default"], fs["kind"], owner=fid)
            self.base_state = self.doc.state
        else:
            self.f = feature
            self.orig_data = copy.deepcopy(feature.data)
            self.orig_exprs = {k: self.doc.params.params[p].expr for k, p in feature.params.items()}
            # make sure every numeric input has a parameter (older docs)
            for fs in self.spec["fields"]:
                if fs["kind"] in NUMERIC_KINDS and fs["key"] not in feature.params:
                    feature.params[fs["key"]] = self.doc.params.add(fs["default"], fs["kind"], owner=feature.id)
            self.base_state = self.doc.state_before(feature.id)
        self.data = copy.deepcopy(self.f.data)
        # Fusion picks Join/Cut/New automatically until the user chooses one
        self.auto_op = ftype == "extrude" and not self.editing
        self.active_field = None
        self.widgets = {}
        self.sel_buttons = {}
        self._build()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.update_preview)
        self.vp.display_state = self.base_state
        self.vp.selection_changed.connect(self._on_selection)
        self.vp.invalidate()
        self.place()
        self.show()
        # pre-selection or first selection field becomes active
        first = next((fs for fs in self.spec["fields"] if fs["kind"] in SELECT_KINDS and fs["kind"] not in ("plane", "axis")), None)
        if first is not None:
            if preselect and not self.editing:
                self._apply_picks(first, preselect)
            self.activate_field(first["key"])
        self.schedule()

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(6)
        title = QLabel(("EDIT " if self.editing else "") + self.spec["label"].upper())
        title.setObjectName("PanelTitle")
        lay.addWidget(title)
        grid = QGridLayout()
        grid.setContentsMargins(10, 4, 10, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.rows = {}
        for r, fs in enumerate(self.spec["fields"]):
            lab = QLabel(fs["label"])
            w = self._make_widget(fs)
            if fs["tip"]:
                w.setToolTip(fs["tip"])
            grid.addWidget(lab, r, 0)
            grid.addWidget(w, r, 1)
            self.rows[fs["key"]] = (lab, w)
        lay.addLayout(grid)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet("color:#c0392b; padding: 0 10px;")
        lay.addWidget(self.msg)
        btns = QHBoxLayout()
        btns.setContentsMargins(10, 0, 10, 0)
        btns.addStretch(1)
        self.ok = QPushButton("OK")
        self.ok.setObjectName("Primary")
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(self.ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)
        self.setFixedWidth(330)
        self._refresh_visibility()

    def _make_widget(self, fs):
        k, key = fs["kind"], fs["key"]
        if k in NUMERIC_KINDS:
            e = ExprEdit(self.doc.params.params[self.f.params[key]].expr, k, self.doc.params.eval_expr)
            e.textChanged.connect(lambda t, key=key, e=e: self._on_expr(key, t, e))
            e.returnPressed.connect(self.accept)
            e.stepped.connect(self.update_preview)
            self.widgets[key] = e
            return e
        if k == "choice":
            c = QComboBox()
            for o in fs["options"]:
                c.addItem(OP_LABELS.get(o, DIRECTION_LABELS.get(o, o)), o)
            c.setCurrentIndex(max(0, fs["options"].index(self.data.get(key, fs["default"]))))
            c.currentIndexChanged.connect(lambda i, key=key, c=c: self._on_choice(key, c.currentData()))
            self.widgets[key] = c
            return c
        if k == "bool":
            c = QCheckBox()
            c.setChecked(bool(self.data.get(key, fs["default"])))
            c.toggled.connect(lambda v, key=key: self._set(key, v))
            self.widgets[key] = c
            return c
        if k in ("plane", "axis"):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            c = QComboBox()
            names = ["XY", "XZ", "YZ"] if k == "plane" else ["X", "Y", "Z"]
            for n in names:
                c.addItem(f"{n} {'Plane' if k == 'plane' else 'Axis'}", n)
            for fid, _ in (self.base_state.planes.items() if k == "plane" else self.base_state.axes.items()):
                feat = self.doc.feature(fid)
                c.addItem(feat.name if feat else fid, {"plane" if k == "plane" else "axis": fid})
            c.addItem("Selected geometry", "__sel__")
            cur = self.data.get(key, fs["default"])
            idx = next((i for i in range(c.count()) if c.itemData(i) == cur), c.count() - 1)
            c.setCurrentIndex(idx)
            c.currentIndexChanged.connect(lambda i, key=key, c=c: self._on_ref_combo(key, c))
            b = QPushButton()
            b.setIcon(icon("search"))
            b.setToolTip("Select in the canvas")
            b.setCheckable(True)
            b.setFixedWidth(32)
            b.clicked.connect(lambda _=False, key=key: self.activate_field(key))
            h.addWidget(c, 1)
            h.addWidget(b)
            self.widgets[key] = c
            self.sel_buttons[key] = b
            return w
        if k in SELECT_KINDS:
            b = QPushButton()
            b.setObjectName("SelButton")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, key=key: self.activate_field(key))
            self.sel_buttons[key] = b
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(b, 1)
            x = QPushButton("✕")
            x.setFixedWidth(28)
            x.setToolTip("Clear selection")
            x.clicked.connect(lambda _=False, key=key: self._clear_field(key))
            h.addWidget(x)
            self._update_sel_label(key)
            return w
        return QLabel("?")

    def _update_sel_label(self, key):
        b = self.sel_buttons.get(key)
        if b is None:
            return
        fs = self._field(key)
        if fs["kind"] in ("plane", "axis"):
            return
        v = self.data.get(key)
        n = len(v) if isinstance(v, list) else (1 if v else 0)
        noun = {"profiles": "profile", "edges": "edge", "faces": "face", "bodies": "body", "body": "body",
                "points": "point", "path": "curve"}.get(fs["kind"], "item")
        if fs["kind"] == "path" and v:
            n = len(v.get("entities", []))
        if fs["kind"] == "edges" and v and any("face" in r for r in v):
            noun = "item"  # mix of faces (all their edges) and edges
        b.setText(f"  {n} {noun}{'s' if n != 1 else ''} selected" if n else f"  Select {noun}s")

    def _field(self, key):
        return next(fs for fs in self.spec["fields"] if fs["key"] == key)

    def _refresh_visibility(self):
        for fs in self.spec["fields"]:
            show = fs["show"] is None or fs["show"](self.data)
            lab, w = self.rows[fs["key"]]
            lab.setVisible(show)
            w.setVisible(show)
        self.adjustSize()

    def place(self):
        self.adjustSize()
        self.move(self.vp.width() - self.width() - 12, 140)

    # ------------------------------------------------------------------ input handlers
    def _on_expr(self, key, text, edit):
        pname = self.f.params[key]
        p = self.doc.params.params[pname]
        try:
            self.doc.params.eval_expr(text, p.kind)
            if pname in self.doc.unused_names(text):
                raise ExpressionError("self reference")
            self.doc.params.set_expr(pname, text)
            edit.setProperty("error", False)
        except ExpressionError as exc:
            edit.setProperty("error", True)
            self.msg.setText(str(exc))
        edit.style().unpolish(edit)
        edit.style().polish(edit)
        self.schedule()

    def _on_choice(self, key, value):
        if key == "operation":
            self.auto_op = False
        self._set(key, value)

    def _set(self, key, value):
        self.data[key] = value
        self._refresh_visibility()
        self.schedule()

    def _on_ref_combo(self, key, combo):
        v = combo.currentData()
        if v == "__sel__":
            self.activate_field(key)
            return
        self.data[key] = v
        self.schedule()

    def _clear_field(self, key):
        fs = self._field(key)
        self.data[key] = [] if fs["kind"] in MULTI and fs["kind"] != "path" else None
        self._update_sel_label(key)
        if self.active_field == key:
            self.vp.set_selection([])
        self.schedule()

    def activate_field(self, key):
        self.active_field = key
        fs = self._field(key)
        for k, b in self.sel_buttons.items():
            b.setChecked(k == key)
        kinds = SELECT_KINDS[fs["kind"]]
        self.vp.show_profiles_for = set(self.base_state.sketches) if "profile" in kinds else set()
        self.vp.show_points = "spoint" in kinds
        self.vp.set_filter(kinds)
        self.vp.selection_changed.disconnect(self._on_selection)
        self.vp.set_selection(self._refs_to_picks(fs))
        self.vp.selection_changed.connect(self._on_selection)
        self.vp.invalidate()
        self.schedule()

    def _on_selection(self):
        if self.active_field is None:
            return
        fs = self._field(self.active_field)
        self._apply_picks(fs, list(self.vp.selection))
        self.schedule()

    def _apply_picks(self, fs, picks):
        """Convert viewport picks into persistent references for a field."""
        st = self.base_state
        k, key = fs["kind"], fs["key"]
        refs = []
        norm_picks = []
        for p in picks:
            try:
                if k == "profiles":
                    if p.kind == "profile":
                        faces = self.vp._profiles_cache.get(p.key) or st.sketches[p.key].profiles
                        sk = st.sketches[p.key]
                        uv = K.interior_point(faces[p.index], sk.frame)
                        refs.append({"sketch": p.key, "uv": [round(uv[0], 9), round(uv[1], 9)]})
                    elif p.kind == "face":
                        face = K.faces(st.bodies[p.key].shape)[p.index]
                        if K.face_info(face)["type"] != "plane":
                            self.msg.setText("Only planar faces can be used as profiles")
                            continue
                        refs.append({"face": R.face_ref(p.key, face)})
                elif k == "edges" and p.kind == "edge":
                    refs.append(R.edge_ref(p.key, K.edges(st.bodies[p.key].shape)[p.index]))
                elif k == "edges" and p.kind == "face":
                    refs.append({"face": R.face_ref(p.key, K.faces(st.bodies[p.key].shape)[p.index])})
                elif k == "faces" and p.kind == "face":
                    refs.append(R.face_ref(p.key, K.faces(st.bodies[p.key].shape)[p.index]))
                elif k in ("bodies", "body") and p.kind in ("face", "body"):
                    if p.key not in refs:
                        refs.append(p.key)
                    p = Pick("body", p.key)
                elif k == "points" and p.kind == "spoint":
                    refs.append({"sketch": p.key, "point": p.index})
                elif k == "path" and p.kind == "curve":
                    refs.append((p.key, p.index))
                elif k == "plane":
                    if p.kind == "plane":
                        refs = [p.key if p.key in K.ORIGIN_FRAMES else {"plane": p.key}]
                    elif p.kind == "face":
                        face = K.faces(st.bodies[p.key].shape)[p.index]
                        if K.face_info(face)["type"] != "plane":
                            self.msg.setText("Select a planar face")
                            continue
                        refs = [{"face": R.face_ref(p.key, face)}]
                    norm_picks = [p]
                    continue
                elif k == "axis":
                    if p.kind == "curve":
                        e = self.vp._sketch_out(p.key).sketch.entities.get(p.index)
                        if e is None or e.kind != "line":
                            continue
                        refs = [{"sketch": p.key, "entity": p.index}]
                    elif p.kind == "edge":
                        refs = [{"edge": R.edge_ref(p.key, K.edges(st.bodies[p.key].shape)[p.index])}]
                    elif p.kind == "face":
                        face = K.faces(st.bodies[p.key].shape)[p.index]
                        if "axis_dir" not in K.face_info(face):
                            continue
                        refs = [{"face": R.face_ref(p.key, face)}]
                    norm_picks = [p]
                    continue
                else:
                    continue
            except (IndexError, KeyError):
                continue
            if p not in norm_picks:
                norm_picks.append(p)
        if k in ("plane", "axis"):
            if refs:
                self.data[key] = refs[0]
                c = self.widgets[key]
                c.blockSignals(True)
                c.setCurrentIndex(c.count() - 1)
                c.blockSignals(False)
        elif k == "body":
            self.data[key] = refs[-1] if refs else None
            norm_picks = norm_picks[-1:]
        elif k == "path":
            sk = refs[0][0] if refs else None
            self.data[key] = {"sketch": sk, "entities": [e for s, e in refs if s == sk]} if refs else None
        else:
            self.data[key] = refs
        if norm_picks != list(self.vp.selection):
            self.vp.selection_changed.disconnect(self._on_selection)
            self.vp.set_selection(norm_picks)
            self.vp.selection_changed.connect(self._on_selection)
        self._update_sel_label(key)

    def _ref_to_pick(self, k, ref):
        """One stored reference -> viewport pick (raises when it cannot be found)."""
        st = self.base_state
        if k == "profiles":
            if "face" in ref:
                bid, face = R.resolve_face(st, ref["face"])
                return Pick("face", bid, _index_of(K.faces(st.bodies[bid].shape), face))
            sk = st.sketches.get(ref["sketch"])
            face = K.profile_at(sk.profiles, sk.frame, ref["uv"]) if sk else None
            if face is None:
                raise R.ReferenceError_("profile no longer exists")
            return Pick("profile", ref["sketch"], _index_of(sk.profiles, face))
        if k == "edges":
            if "face" in ref:
                bid, f = R.resolve_face(st, ref["face"])
                return Pick("face", bid, _index_of(K.faces(st.bodies[bid].shape), f))
            bid, e = R.resolve_edge(st, ref)
            return Pick("edge", bid, _index_of(K.edges(st.bodies[bid].shape), e))
        if k == "faces":
            bid, f = R.resolve_face(st, ref)
            return Pick("face", bid, _index_of(K.faces(st.bodies[bid].shape), f))
        if k == "bodies":
            if ref not in st.bodies:
                raise R.ReferenceError_("body no longer exists")
            return Pick("body", ref)
        if k == "points":
            sk = st.sketches.get(ref["sketch"])
            if sk is None or ref["point"] not in sk.sketch.entities:
                raise R.ReferenceError_("sketch point no longer exists")
            return Pick("spoint", ref["sketch"], ref["point"])
        raise R.ReferenceError_("unsupported reference")

    def _refs_to_picks(self, fs):
        """Re-create viewport picks from stored references (editing).  References
        that can no longer be found are dropped and reported so the user can
        simply re-select them (the 'repair lost references' flow)."""
        k, v = fs["kind"], self.data.get(fs["key"])
        out, lost = [], 0
        if k == "body":
            out = [Pick("body", v)] if v in self.base_state.bodies else []
            lost = 1 if v and not out else 0
        elif k == "path":
            if v:
                sk = self.base_state.sketches.get(v["sketch"])
                keep = [e for e in v["entities"] if sk is not None and e in sk.sketch.entities]
                lost = len(v["entities"]) - len(keep)
                out = [Pick("curve", v["sketch"], e) for e in keep]
        elif k in ("profiles", "edges", "faces", "bodies", "points"):
            for ref in v or []:
                try:
                    out.append(self._ref_to_pick(k, ref))
                except Exception:
                    lost += 1
        if lost:
            self.msg.setText(f"{lost} reference(s) in '{fs['label']}' could not be found after earlier changes - "
                             "re-select them in the model, then press OK")
            self._lost_refs = getattr(self, "_lost_refs", 0) + lost
        return out

    # ------------------------------------------------------------------ preview
    def schedule(self):
        self._timer.start()

    def _temp_feature(self):
        data = copy.deepcopy(self.data)
        if self.auto_op:
            data["operation"] = "auto"
        return Feature(self.f.id, self.ftype, self.f.name, data, dict(self.f.params))

    def update_preview(self):
        f = self._temp_feature()
        st = self.base_state.copy()
        self.msg.setText("")
        try:
            self.doc.params._cache.clear()
            execute(self.doc, f, st)
            self.ok.setEnabled(True)
            resolved = getattr(f, "resolved_operation", None)
            if self.auto_op and resolved:
                self.data["operation"] = resolved
                c = self.widgets.get("operation")
                if c is not None:
                    c.blockSignals(True)
                    c.setCurrentIndex(max(0, c.findData(resolved)))
                    c.setItemText(c.currentIndex(), OP_LABELS[resolved] + "  (auto)")
                    c.blockSignals(False)
                self._refresh_visibility()
            if f.warning:
                self.msg.setText(f.warning)
        except Exception as exc:
            self.msg.setText(str(exc) or type(exc).__name__)
            self.vp.set_previews([])
            self.vp.hidden_bodies = set()
            self.ok.setEnabled(not self._missing_required())
            self._update_manipulators()
            return
        previews, hidden = [], set()
        for bid, b in st.bodies.items():
            old = self.base_state.bodies.get(bid)
            if old is None or old.token != b.token:
                previews.append((b.shape, (0.35, 0.62, 0.95) if old is None else (0.95, 0.62, 0.30), 0.55))
                if old is not None:
                    hidden.add(bid)
        for bid in self.base_state.bodies:
            if bid not in st.bodies:
                hidden.add(bid)
        selecting_geometry = self.active_field is not None and \
            self._field(self.active_field)["kind"] in ("edges", "faces")
        self.vp.hidden_bodies = set() if selecting_geometry else hidden
        self.vp.set_previews(previews)
        self._update_manipulators()

    # ------------------------------------------------------------------ in-canvas handles
    def _set_value(self, key, value_mm, final, fmt="length"):
        from ..core.expressions import format_angle, format_length
        txt = format_length(value_mm, digits=3) if fmt == "length" else format_angle(value_mm)
        e = self.widgets[key]
        e.blockSignals(True)
        e.setText(txt)
        e.blockSignals(False)
        self._on_expr(key, txt, e)
        if final:
            self._timer.stop()
            self.update_preview()

    def _manip_specs(self):
        """(key, origin, direction, value, scale) tuples for the current inputs."""
        st = self.base_state
        d, out = self.data, []
        val = lambda k: self.doc.params.value(self.f.params[k])  # noqa: E731
        try:
            if self.ftype == "extrude" and d.get("profiles"):
                from ..core.features import _profile_normal
                ref = d["profiles"][0]
                face, _ = R.resolve_profile(st, ref)
                c = K.centroid(face)
                n = _profile_normal(st, ref, face)
                if d.get("direction") == "symmetric":
                    out.append(("distance", c, n, val("distance") / 2, 2.0))
                else:
                    out.append(("distance", c, n, val("distance"), 1.0))
                    if d.get("direction") == "two_sides":
                        out.append(("distance2", c, -n, val("distance2"), 1.0))
            elif self.ftype == "plane_offset":
                fr = R.resolve_plane(st, d.get("plane", "XY"))
                out.append(("distance", fr.origin, fr.normal, val("distance"), 1.0))
            elif self.ftype in ("fillet", "chamfer") and d.get("edges"):
                ref = d["edges"][0]
                if "face" in ref:
                    bid, f = R.resolve_face(st, ref["face"])
                    e = K.edges(f)[0]
                else:
                    bid, e = R.resolve_edge(st, ref)
                info = K.edge_info(e)
                mid = np.array(info["mid"])
                body_c = K.centroid(st.bodies[bid].shape)
                t = np.array(info["tangent"])
                v = body_c - mid
                v -= np.dot(v, t) * t
                if np.linalg.norm(v) > 1e-9:
                    v = v / np.linalg.norm(v)
                    key = "radius" if self.ftype == "fillet" else "distance"
                    out.append((key, mid, v, val(key), 1.0))
            elif self.ftype == "shell" and d.get("faces"):
                bid, f = R.resolve_face(st, d["faces"][0])
                info = K.face_info(f)
                out.append(("thickness", np.array(info["center"]), -np.array(info["normal"]),
                            val("thickness"), 1.0))
        except Exception:
            return []
        return out

    def _update_manipulators(self):
        from ..core.expressions import format_length
        from .viewport import Manipulator
        manips = []
        for key, o, n, v, scale in self._manip_specs():
            def cb(t, final, key=key, scale=scale):
                self._set_value(key, t * scale, final)
            manips.append(Manipulator(np.asarray(o, float), np.asarray(n, float), float(v), cb,
                                      format_length(v * scale), "arrow",
                                      0.0 if key in ("radius", "thickness") or self.ftype == "chamfer" else None))
        if self.vp._manip_drag is None:
            self.vp.set_manipulators(manips)
        else:  # keep the dragged handle, refresh its label
            m = self.vp._manip_drag
            m.label = format_length(m.value)

    def _missing_required(self):
        for fs in self.spec["fields"]:
            if fs["kind"] in MULTI and not fs["optional"] and not self.data.get(fs["key"]):
                return True
        return False

    # ------------------------------------------------------------------ finish
    def _cleanup(self):
        self._timer.stop()
        try:
            self.vp.selection_changed.disconnect(self._on_selection)
        except (RuntimeError, TypeError):
            pass
        self.vp.display_state = None
        self.vp.hidden_bodies = set()
        self.vp.show_profiles_for = set()
        self.vp.show_points = False
        self.vp.set_previews([])
        self.vp.set_manipulators([])
        self.vp.set_filter(None)
        self.vp.set_selection([])
        self.vp.invalidate()
        self.hide()
        self.deleteLater()

    def accept(self):
        doc = self.doc
        if self._timer.isActive():  # make sure auto-operation etc. reflect the latest inputs
            self._timer.stop()
            self.update_preview()
        label = ("Edit " if self.editing else "") + self.spec["label"]
        try:
            if self.editing:
                self.f.data = copy.deepcopy(self.data)
                doc.rebuild()
            else:
                self.f.data = copy.deepcopy(self.data)
                doc.insert_feature(self.f)
                self._auto_hide_sketches()
        except Exception as exc:
            self.msg.setText(str(exc))
            return
        doc.push_undo(label, self.snapshot)
        self._cleanup()
        self.finished.emit(True)

    def _auto_hide_sketches(self):
        """Fusion hides a sketch once a feature consumes its profiles."""
        for key in ("profiles", "path"):
            v = self.data.get(key)
            refs = v if isinstance(v, list) else ([v] if v else [])
            for r in refs:
                if isinstance(r, dict) and "sketch" in r:
                    self.doc.body_props.setdefault(r["sketch"], {})["visible"] = False

    def reject(self):
        doc = self.doc
        if self.editing:
            self.f.data = self.orig_data
            for k, e in self.orig_exprs.items():
                try:
                    doc.params.set_expr(self.f.params[k], e)
                except ExpressionError:
                    pass
        else:
            doc.params.remove_owned_by(self.f.id)
        doc.params._cache.clear()
        self._cleanup()
        self.finished.emit(False)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(ev)


def _index_of(shapes, s):
    for i, x in enumerate(shapes):
        if x.IsSame(s):
            return i
    return -1
