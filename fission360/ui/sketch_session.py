"""Sketch editing mode: tools, constraints, dimensions and undo while sketching."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLineEdit

from ..core.expressions import ExpressionError, format_angle, format_length
from ..sketch.model import DIMENSION_KINDS, SketchError
from . import sketch_tools as T
from .viewport import Pick


class InlineEditor(QLineEdit):
    """Floating value box used to type dimension values/expressions."""

    def __init__(self, parent, text, on_commit, on_cancel=None):
        super().__init__(text, parent)
        self.on_commit = on_commit
        self.on_cancel = on_cancel
        self.setWindowFlags(Qt.Popup)
        self.setMinimumWidth(140)
        self.selectAll()
        self.returnPressed.connect(self._commit)
        self._done = False

    def _commit(self):
        try:
            self.on_commit(self.text())
        except (ExpressionError, SketchError) as exc:
            self.setProperty("error", True)
            self.setToolTip(str(exc))
            self.style().unpolish(self)
            self.style().polish(self)
            return
        self._done = True
        self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self._done = True
            if self.on_cancel:
                self.on_cancel()
            self.close()
            return
        super().keyPressEvent(ev)


class SketchSession:
    def __init__(self, win, fid: str):
        self.win = win
        self.doc = win.doc
        self.vp = win.viewport
        self.fid = fid
        self.grid_snap = False
        self.tool = None
        doc = self.doc
        i = doc.index_of(fid)
        self.saved_marker = doc.marker
        at_end = doc.marker >= len(doc.features)
        self.restore_to_end = at_end
        # roll the timeline to just after the sketch (Fusion behaviour)
        doc.marker = i + 1
        doc.rebuild()
        self.frame = doc.state.sketches[fid].frame if fid in doc.state.sketches else None
        if self.frame is None:
            from ..core import references as R
            self.frame = R.resolve_plane(doc.state_before(fid), doc.feature(fid).data.get("plane", "XY"))
        self.snap = doc.snapshot()
        self.vp.sketch_ctx = (fid, self.sketch, self.frame)
        self.vp.set_filter(None)
        self.vp.clear_selection()
        self.vp.invalidate()
        self.set_tool(None)

    @property
    def feature(self):
        return self.doc.feature(self.fid)

    @property
    def sketch(self):
        return self.feature.sketch

    # ------------------------------------------------------------------ plumbing
    def message(self, text):
        self.win.statusBar().showMessage(text, 5000)

    def live_update(self):
        # driven (reference) dimensions display the measured value
        sk = self.sketch
        for c in sk.constraints.values():
            if c.driven and c.param in self.doc.params.params:
                try:
                    v = sk.measure(c.kind, c.refs)
                    txt = format_angle(v) if c.kind == "angle" else format_length(v)
                    if self.doc.params.params[c.param].expr != txt:
                        self.doc.params.set_expr(c.param, txt)
                except (SketchError, KeyError, ExpressionError):
                    pass
        self.vp.sketch_ctx = (self.fid, self.sketch, self.frame)
        self.vp.scene_dirty = True
        self.vp.update()
        self.win.update_sketch_status()

    def changed(self, label):
        """Record an undo step after a sketch modification."""
        self.doc.push_undo(label, self.snap)
        self.snap = self.doc.snapshot()
        self.live_update()

    def on_history(self):
        """Undo/redo replaced the feature objects: re-bind."""
        if self.doc.feature(self.fid) is None:
            self.win.finish_sketch(cancelled=True)
            return
        self.snap = self.doc.snapshot()
        self.sketch.param_value = self.doc.param_value
        self.sketch.solve()
        self.live_update()

    def set_tool(self, name):
        if self.tool is not None:
            self.tool.finish(self.vp)
        cls = T.TOOLS.get(name) if name else T.SelectTool
        self.tool = cls(self)
        self.vp.tool = self.tool
        self.vp.clear_selection()
        self.win.sketch_tool_changed(name)
        if self.tool.hint:
            self.message(self.tool.hint)
        self.vp.update()

    def highlight(self, items):
        picks = [Pick(kind, self.fid, idx) for kind, idx in items]
        self.vp.selection = picks
        self.vp.scene_dirty = True
        self.vp.update()

    def finish(self):
        if self.tool is not None:
            self.tool.finish(self.vp)
        self.vp.tool = None
        self.vp.sketch_ctx = None
        doc = self.doc
        doc.marker = len(doc.features) if self.restore_to_end else max(self.saved_marker, doc.index_of(self.fid) + 1)
        doc.rebuild()
        self.vp.invalidate()

    # ------------------------------------------------------------------ selection helpers
    def selected_refs(self):
        out = []
        for p in self.vp.selection:
            if p.key != self.fid:
                continue
            if p.kind in ("curve", "spoint"):
                out.append(p.index)
            elif p.kind == "origin":
                out.append(0)
        return out

    def selected_constraints(self):
        return [p.index for p in self.vp.selection if p.kind == "constraint"]

    # ------------------------------------------------------------------ constraints
    def apply_constraint(self, kind):
        sk = self.sketch
        refs = self.selected_refs()
        E = sk.entities
        kinds = [E[r].kind for r in refs if r in E]
        try:
            if kind == "fix":
                if not refs:
                    raise SketchError("Select geometry to fix")
                for r in refs:
                    existing = [cid for cid, c in sk.constraints.items() if c.kind == "fix" and c.refs == [r]]
                    if existing:
                        for cid in existing:
                            del sk.constraints[cid]
                    else:
                        sk.add_constraint("fix", [r])
            elif kind in ("horizontal", "vertical"):
                lines = [r for r in refs if E[r].kind == "line"]
                pts = [r for r in refs if E[r].kind == "point"]
                if lines:
                    for l in lines:
                        sk.add_constraint(kind, [l])
                elif len(pts) == 2:
                    sk.add_constraint(kind, pts)
                else:
                    raise SketchError("Select lines or two points")
            elif kind in ("parallel", "perpendicular", "collinear"):
                if kinds != ["line", "line"]:
                    raise SketchError("Select two lines")
                sk.add_constraint(kind, refs)
            elif kind == "equal":
                if len(refs) < 2 or len(set(k if k != "arc" else "circle" for k in kinds)) != 1:
                    raise SketchError("Select two or more lines, or circles/arcs")
                for r in refs[1:]:
                    sk.add_constraint("equal", [refs[0], r])
            elif kind == "coincident":
                if len(refs) != 2 or "point" not in kinds:
                    raise SketchError("Select a point and a point or curve")
                sk.add_constraint("coincident", refs)
            elif kind == "tangent":
                if len(refs) != 2 or not any(k in ("circle", "arc") for k in kinds):
                    raise SketchError("Select a line/arc and a circle/arc")
                sk.add_constraint("tangent", refs)
            elif kind == "concentric":
                if len(refs) != 2 or not all(k in ("circle", "arc") for k in kinds):
                    raise SketchError("Select two circles/arcs")
                sk.add_constraint("concentric", refs)
            elif kind == "midpoint":
                if sorted(kinds) != ["line", "point"]:
                    raise SketchError("Select a point and a line")
                sk.add_constraint("midpoint", refs)
            elif kind == "symmetric":
                if len(refs) != 3 or kinds[2] != "line":
                    pts = [r for r in refs if E[r].kind == "point"]
                    ln = [r for r in refs if E[r].kind == "line"]
                    if len(pts) == 2 and len(ln) == 1:
                        refs = pts + ln
                    elif len(ln) == 3:  # two lines symmetric about a third: use endpoints
                        a, b, axis = ln
                        sk.add_constraint("symmetric", [E[a].pts[0], E[b].pts[0], axis])
                        sk.add_constraint("symmetric", [E[a].pts[1], E[b].pts[1], axis])
                        refs = None
                    else:
                        raise SketchError("Select two points (or lines) and a symmetry line")
                if refs:
                    sk.add_constraint("symmetric", refs)
            else:
                raise SketchError(f"Unknown constraint {kind}")
        except SketchError as exc:
            self.message(str(exc))
            return
        sk.solve()
        self.vp.clear_selection()
        self.changed(f"{kind.title()} constraint")

    def toggle_construction(self):
        sk = self.sketch
        refs = [r for r in self.selected_refs() if sk.entities[r].kind != "point"]
        if not refs:
            self.message("Select curves to toggle construction")
            return
        for r in refs:
            sk.entities[r].construction = not sk.entities[r].construction
        self.changed("Toggle construction")

    def delete_selection(self):
        sk = self.sketch
        cons = self.selected_constraints()
        refs = self.selected_refs()
        if not cons and not refs:
            return
        for cid in cons:
            c = sk.constraints.get(cid)
            if c is not None:
                if c.param:
                    self.doc.params.params.pop(c.param, None)
                sk.remove(cid)
        for r in refs:
            if r in sk.entities:
                params = [c.param for c in sk.constraints.values() if r in c.refs and c.param]
                sk.remove(r)
                for p in params:
                    if not any(c.param == p for c in sk.constraints.values()):
                        self.doc.params.params.pop(p, None)
        self.doc.params._cache.clear()
        sk.solve()
        self.vp.clear_selection()
        self.changed("Delete sketch geometry")

    # ------------------------------------------------------------------ dimensions
    def add_dimension(self, kind, refs, value, label_uv, expr=None, commit=True):
        """Create a driving dimension.  ``expr`` keeps a typed expression
        (e.g. ``width/2``) instead of the measured number."""
        sk = self.sketch
        pkind = DIMENSION_KINDS[kind]
        text = format_angle(value) if pkind == "angle" else format_length(value)
        try:
            pname = self.doc.params.add(expr if expr else text, pkind, owner=self.fid)
        except ExpressionError:
            pname = self.doc.params.add(text, pkind, owner=self.fid)
        c_id = None
        try:
            c_id = sk.add_constraint(kind, refs, param=pname)
        except SketchError:
            # over-constrained: create a driven (reference) dimension, like Fusion
            c_id = sk.add_constraint(kind, refs, param=pname, driven=True)
            self.message("Dimension would over-constrain the sketch: created as driven dimension")
        c = sk.constraints[c_id]
        try:
            import numpy as np
            mid = self._dim_mid(c)
            if mid is not None and kind not in ("radius", "diameter", "angle"):
                c.data["offset"] = (np.asarray(label_uv) - mid).tolist()
            elif kind in ("radius", "diameter"):
                ctr = np.array(sk.xy(sk.entities[refs[0]].pts[0]))
                d = np.asarray(label_uv) - ctr
                c.data["ang"] = math.atan2(d[1], d[0])
            elif kind == "angle":
                c.data["offset"] = [0.0, 0.0]
        except Exception:
            pass
        if commit:
            self.changed("Dimension")
        return c_id

    def _dim_mid(self, c):
        import numpy as np
        sk = self.sketch
        pts = []
        for r in c.refs:
            e = sk.entities[r]
            if e.kind == "point":
                pts.append(np.array(sk.xy(r)))
            elif e.kind == "line":
                pts += [np.array(sk.xy(e.pts[0])), np.array(sk.xy(e.pts[1]))]
            else:
                pts.append(np.array(sk.xy(e.pts[0])))
        return np.mean(pts, axis=0) if pts else None

    # ------------------------------------------------------------------ modify commands
    def _selected_curves(self):
        sk = self.sketch
        return [r for r in self.selected_refs() if r in sk.entities and sk.entities[r].kind not in ("point",)]

    def _select_new(self, ids):
        from .viewport import Pick
        self.vp.selection = [Pick("curve", self.fid, i) for i in ids]
        self.live_update()

    def edit_text(self, eid):
        from .dialogs import TextDialog
        e = self.sketch.entities[eid]
        dlg = TextDialog(self.vp, self.doc, e)
        if dlg.exec():
            v = dlg.values()
            e.text, e.height, e.font, e.bold, e.italic, e.angle = (v["text"], v["height"], v["font"], v["bold"],
                                                                   v["italic"], v["angle"])
            self.changed("Edit text")

    def offset(self):
        from ..sketch import ops
        from .dialogs import ValuesDialog
        ids = self._selected_curves()
        if not ids:
            self.message("Select the curves to offset first")
            return
        dlg = ValuesDialog(self.vp, self.doc, "Offset", [("Distance", "length", "2 mm")],
                           note="Positive = left of the curve direction / outward for counter-clockwise loops")
        if not dlg.exec():
            return
        try:
            new = ops.offset_curves(self.sketch, ids, dlg.values()[0], self.frame)
        except SketchError as exc:
            self.message(str(exc))
            return
        self.sketch.solve()
        self.changed("Offset")
        self._select_new(new)

    def mirror(self):
        from ..sketch import ops
        sk = self.sketch
        sel = self._selected_curves()
        lines = [r for r in sel if sk.entities[r].kind == "line"]
        if len(sel) < 2 or not lines:
            self.message("Select the curves to mirror, then the mirror line last (e.g. a construction line)")
            return
        axis = lines[-1]
        objs = [r for r in sel if r != axis]
        try:
            new = ops.mirror_curves(sk, objs, axis)
        except SketchError as exc:
            self.message(str(exc))
            return
        sk.solve()
        self.changed("Mirror")
        self._select_new(new)

    def pattern_rect(self):
        from ..sketch import ops
        from .dialogs import ValuesDialog
        ids = self._selected_curves()
        if not ids:
            self.message("Select the curves to pattern first")
            return
        dlg = ValuesDialog(self.vp, self.doc, "Rectangular Pattern",
                           [("Count X", "scalar", "3"), ("Spacing X", "length", "10 mm"),
                            ("Count Y", "scalar", "1"), ("Spacing Y", "length", "10 mm")])
        if not dlg.exec():
            return
        nx, dx, ny, dy = dlg.values()
        if nx * ny > 400:
            self.message("Pattern too large (max 400 instances)")
            return
        new = ops.pattern_rect(self.sketch, ids, max(1, int(round(nx))), dx, max(1, int(round(ny))), dy)
        self.sketch.solve()
        self.changed("Rectangular pattern")
        self._select_new(new)

    def pattern_circ(self):
        from ..sketch import ops
        from .dialogs import ValuesDialog
        sk = self.sketch
        ids = self._selected_curves()
        pts = [r for r in self.selected_refs() if sk.entities[r].kind == "point"]
        if not ids:
            self.message("Select the curves to pattern (and optionally a center point)")
            return
        dlg = ValuesDialog(self.vp, self.doc, "Circular Pattern",
                           [("Count", "scalar", "6"), ("Total angle", "angle", "360 deg")],
                           note="Pattern center: the selected sketch point, else the sketch origin")
        if not dlg.exec():
            return
        count, ang = dlg.values()
        center = sk.xy(pts[0]) if pts else (0.0, 0.0)
        new = ops.pattern_circ(sk, ids, center, max(2, int(round(count))), ang)
        sk.solve()
        self.changed("Circular pattern")
        self._select_new(new)

    def import_2d(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..sketch import ops
        path, _ = QFileDialog.getOpenFileName(self.vp, "Insert DXF / SVG into sketch", "",
                                              "2D drawings (*.dxf *.svg);;All files (*)")
        if not path:
            return
        try:
            new = ops.import_2d_file(self.sketch, path)
        except Exception as exc:
            QMessageBox.warning(self.vp, "Import", f"Could not import: {exc}")
            return
        self.sketch.solve()
        self.changed("Insert drawing")
        self._select_new(new)
        self.message(f"Inserted {len(new)} curves - drag or constrain them into place")

    def export_dxf(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..sketch import ops
        path, _ = QFileDialog.getSaveFileName(self.vp, "Export sketch as DXF", f"{self.feature.name}.dxf", "DXF (*.dxf)")
        if not path:
            return
        try:
            ops.write_dxf(self.sketch, path if path.endswith(".dxf") else path + ".dxf")
            self.message(f"Exported {path}")
        except OSError as exc:
            QMessageBox.warning(self.vp, "Export", str(exc))

    def edit_dimension(self, cid, global_pos: QPoint | None = None):
        sk = self.sketch
        c = sk.constraints.get(cid)
        if c is None or not c.param:
            return
        p = self.doc.params.params[c.param]
        old = p.expr
        if c.driven:
            self.message("Driven dimensions are measured, not editable")
            return

        def commit(text):
            self.doc.params.set_expr(c.param, text)
            res = sk.solve()
            if not res.ok:
                self.doc.params.set_expr(c.param, old)
                sk.solve()
                raise SketchError("Value cannot be solved")
            self.changed("Edit dimension")

        if global_pos is None:
            global_pos = self.vp.mapToGlobal(self.vp.rect().center())
        ed = InlineEditor(None, old, commit)
        ed.move(global_pos + QPoint(8, 8))
        ed.show()
        ed.setFocus()
        self._editor = ed
