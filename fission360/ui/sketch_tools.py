"""Interactive sketch tools: drawing with snapping & auto-constraints,
dimensions, trim, sketch fillet, projection and direct dragging.

All tools work in sketch-plane coordinates (u, v).  Snapping priority:
existing point > curve > horizontal/vertical inference > grid.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from ..core import kernel as K
from ..core.expressions import format_angle, format_length
from ..sketch import geometry2d as g2
from ..sketch.model import SketchError
from .theme import THEME

SNAP_PX = 10.0


class Snap:
    def __init__(self, uv, kind="free", ref=None, hv=None):
        self.uv = np.asarray(uv, float)
        self.kind = kind     # free | point | curve | grid
        self.ref = ref       # point id or curve id
        self.hv = hv         # inferred alignment: ('h'|'v', pid)


class SketchTool:
    name = "tool"
    hint = ""

    def __init__(self, session):
        self.s = session

    # helpers -------------------------------------------------------------
    @property
    def sk(self):
        return self.s.sketch

    @property
    def fr(self):
        return self.s.frame

    def px(self, vp):
        return vp.cam.pixel_size_at(self.fr.origin)

    def snap(self, vp, x, y, exclude=(), infer_from=None) -> Snap | None:
        uv = vp.plane_point(x, y, self.fr)
        if uv is None:
            return None
        tol = SNAP_PX * self.px(vp)
        best = None
        for p in self.sk.points():
            if p.id in exclude:
                continue
            d = math.dist(uv, (p.x, p.y))
            if d < tol and (best is None or d < best[0]):
                best = (d, p.id)
        if best:
            return Snap(self.sk.xy(best[1]), "point", best[1])
        # curve snap
        bc = None
        for e in self.sk.curves():
            if e.id in exclude or set(e.pts) & set(exclude):
                continue
            q, d = g2.nearest_on_curve(self.sk, e, uv)
            if d < tol * 0.8 and (bc is None or d < bc[0]):
                bc = (d, e.id, q)
        snap = Snap(uv)
        if bc:
            snap = Snap(bc[2], "curve", bc[1])
        # horizontal / vertical inference against the anchor point
        if infer_from is not None and snap.kind == "free":
            a = np.array(self.sk.xy(infer_from)) if not isinstance(infer_from, np.ndarray) else infer_from
            d = snap.uv - a
            if abs(d[1]) < tol * 0.7 and abs(d[0]) > tol:
                snap = Snap((snap.uv[0], a[1]), "free", hv=("h", infer_from))
            elif abs(d[0]) < tol * 0.7 and abs(d[1]) > tol:
                snap = Snap((a[0], snap.uv[1]), "free", hv=("v", infer_from))
        if snap.kind == "free" and snap.hv is None and self.s.grid_snap:
            step = getattr(vp, "grid_step", 1.0) or 1.0
            snap = Snap(np.round(snap.uv / step) * step, "grid")
        return snap

    def attach(self, pid, snap: Snap):
        """Add coincidence for a new point created at a snap location."""
        if snap is None:
            return
        try:
            if snap.kind == "point" and snap.ref != pid:
                self.sk.add_constraint("coincident", [pid, snap.ref])
            elif snap.kind == "curve":
                e = self.sk.entities.get(snap.ref)
                if e is not None and e.kind != "spline" and pid not in e.pts:
                    self.sk.add_constraint("coincident", [pid, snap.ref])
        except SketchError:
            pass

    def point_for(self, snap: Snap):
        """Reuse a snapped point id when possible (keeps sketches tidy)."""
        return self.sk.add_point(*snap.uv)

    def preview(self, vp, polylines, points=()):
        vp.tool_lines.clear()
        vp.tool_points.clear()
        for pl in polylines:
            vp.tool_lines.add_polyline(self.fr.to_world(np.asarray(pl)), (*THEME.sk_free, 0.9))
        for p in points:
            vp.tool_points.add_points(self.fr.to_world(np.asarray(p)), (*THEME.hover, 1.0))
        vp.update()

    def snap_marker(self, vp, snap):
        vp.tool_points.clear()
        if snap is not None and snap.kind in ("point", "curve"):
            vp.tool_points.add_points(self.fr.to_world(snap.uv), (*THEME.hover, 1.0))

    def finish(self, vp):
        """Called when the tool is deactivated."""
        vp.tool_lines.clear()
        vp.tool_points.clear()
        vp.labels = []

    def key(self, vp, ev):
        if ev.key() == Qt.Key_Escape:
            if self.cancel_step(vp):
                return True
            self.s.set_tool(None)
            return True
        return False

    def cancel_step(self, vp) -> bool:
        return False

    def right_click(self, vp, x, y):
        if self.cancel_step(vp):
            return True
        return False

    def commit(self, label):
        self.s.changed(label)

    def length_label(self, vp, a, b):
        mid = self.fr.to_world((np.asarray(a) + np.asarray(b)) / 2)
        vp.labels = [(mid, format_length(math.dist(a, b)), THEME.sk_free)]


# ---------------------------------------------------------------------------
class SelectTool(SketchTool):
    """Default sketch tool: select & drag geometry (solver keeps constraints)."""
    name = "select"

    def __init__(self, session):
        super().__init__(session)
        self.drag = None

    def press(self, vp, x, y, ev):
        p = vp.pick_at(x, y, {"spoint", "curve"})
        if p is None or p.key != self.s.fid:
            return False
        uv = vp.plane_point(x, y, self.fr)
        if p.kind == "spoint":
            if self.sk.entities[p.index].fixed:
                return False
            self.drag = ("point", p.index, uv)
        else:
            e = self.sk.entities[p.index]
            self.drag = ("curve", e.id, uv, {pid: np.array(self.sk.xy(pid)) for pid in e.pts})
        self.dragged = False
        return False  # still allow click selection on release

    def move(self, vp, x, y, ev):
        if self.drag is None or not (ev.buttons() & Qt.LeftButton):
            return False
        uv = vp.plane_point(x, y, self.fr)
        if uv is None:
            return True
        self.dragged = True
        if self.drag[0] == "point":
            self.sk.solve(drag={self.drag[1]: tuple(uv)}, analyse=False)
        else:
            d = uv - self.drag[2]
            targets = {pid: tuple(p0 + d) for pid, p0 in self.drag[3].items()}
            self.sk.solve(drag=targets, analyse=False)
        self.s.live_update()
        return True

    def release(self, vp, x, y, ev):
        if self.drag is not None and getattr(self, "dragged", False):
            self.drag = None
            self.sk.solve()
            self.commit("Drag sketch geometry")
            return True
        self.drag = None
        return False


# ---------------------------------------------------------------------------
class LineTool(SketchTool):
    name = "line"
    hint = "Click to place points. Click the first point to close, Esc to finish."

    def __init__(self, session):
        super().__init__(session)
        self.reset_state()

    def reset_state(self):
        self.start: Snap | None = None   # snap of the chain's current start
        self.prev_end: int | None = None  # end point id of the previous segment
        self.first_pid: int | None = None

    def _anchor(self):
        if self.start is None:
            return None
        return self.prev_end if self.prev_end is not None else np.array(self.start.uv)

    def move(self, vp, x, y, ev):
        sn = self.snap(vp, x, y, infer_from=self._anchor(),
                       exclude=(self.prev_end,) if self.prev_end is not None else ())
        if sn is None:
            return True
        if self.start is not None:
            a = self.sk.xy(self.prev_end) if self.prev_end is not None else self.start.uv
            self.preview(vp, [[a, sn.uv]], [sn.uv] if sn.kind != "free" else [])
            self.length_label(vp, a, sn.uv)
        else:
            self.snap_marker(vp, sn)
        return True

    def press(self, vp, x, y, ev):
        sn = self.snap(vp, x, y, infer_from=self._anchor(),
                       exclude=(self.prev_end,) if self.prev_end is not None else ())
        if sn is None:
            return True
        if self.start is None:
            self.start = sn
            return True
        a = self.sk.xy(self.prev_end) if self.prev_end is not None else self.start.uv
        if math.dist(a, sn.uv) < 1e-6:
            return True
        lid = self.sk.add_line(a, sn.uv)
        p0, p1 = self.sk.entities[lid].pts
        if self.prev_end is not None:
            self.sk.add_constraint("coincident", [p0, self.prev_end], check=False)
        else:
            self.attach(p0, self.start)
            self.first_pid = p0
        closed = sn.kind == "point" and sn.ref == self.first_pid
        self.attach(p1, sn)
        if sn.hv is not None:
            try:
                self.sk.add_constraint("horizontal" if sn.hv[0] == "h" else "vertical", [lid])
            except SketchError:
                pass
        self.sk.solve()
        self.commit("Line")
        if closed or sn.kind == "point":
            # closed a loop or joined existing geometry: start a fresh chain
            self.reset(vp)
            return True
        self.prev_end = p1
        self.start = sn
        return True

    def reset(self, vp):
        self.reset_state()
        vp.tool_lines.clear()
        vp.labels = []
        self.s.live_update()

    def cancel_step(self, vp):
        if self.start is not None:
            self.reset(vp)
            return True
        return False

    def double_click(self, vp, x, y):
        self.reset(vp)
        return True


# ---------------------------------------------------------------------------
class TwoClickTool(SketchTool):
    """Base for tools defined by successive clicks (rect, circle, arc ...)."""
    clicks_needed = 2

    def __init__(self, session):
        super().__init__(session)
        self.pts: list[Snap] = []
        self.cur = None

    def move(self, vp, x, y, ev):
        anchor = np.array(self.pts[0].uv) if self.pts else None
        sn = self.snap(vp, x, y, infer_from=anchor)
        self.cur = sn
        if sn is None:
            return True
        if self.pts:
            self.draw_preview(vp, [p.uv for p in self.pts] + [sn.uv])
        else:
            self.snap_marker(vp, sn)
        return True

    def press(self, vp, x, y, ev):
        anchor = np.array(self.pts[0].uv) if self.pts else None
        sn = self.snap(vp, x, y, infer_from=anchor)
        if sn is None:
            return True
        self.pts.append(sn)
        if len(self.pts) >= self.clicks_needed:
            try:
                self.create(self.pts)
                self.sk.solve()
                self.commit(self.label)
            except (SketchError, ValueError, ZeroDivisionError):
                pass
            self.pts = []
            vp.tool_lines.clear()
            vp.labels = []
            self.s.live_update()
        return True

    def cancel_step(self, vp):
        if self.pts:
            self.pts = []
            vp.tool_lines.clear()
            vp.labels = []
            return True
        return False

    def draw_preview(self, vp, uvs):
        pass

    def create(self, snaps):
        raise NotImplementedError


def _rect_corners(a, b):
    return [np.array(a), np.array([b[0], a[1]]), np.array(b), np.array([a[0], b[1]])]


class RectTool(TwoClickTool):
    name = "rect"
    label = "Rectangle"
    hint = "Click two opposite corners."
    center = False

    def corners(self, a, b):
        if self.center:
            a = np.asarray(a)
            b = np.asarray(b)
            return _rect_corners(2 * a - b, b)
        return _rect_corners(a, b)

    def draw_preview(self, vp, uvs):
        c = self.corners(uvs[0], uvs[1])
        self.preview(vp, [c + [c[0]]])
        w, h = abs(c[2][0] - c[0][0]), abs(c[2][1] - c[0][1])
        vp.labels = [(self.fr.to_world((c[0] + c[1]) / 2), format_length(w), THEME.sk_free),
                     (self.fr.to_world((c[1] + c[2]) / 2), format_length(h), THEME.sk_free)]

    def create(self, snaps):
        c = self.corners(snaps[0].uv, snaps[1].uv)
        if abs(c[2][0] - c[0][0]) < 1e-6 or abs(c[2][1] - c[0][1]) < 1e-6:
            raise ValueError("degenerate rectangle")
        sk = self.sk
        lines = [sk.add_line(c[i], c[(i + 1) % 4]) for i in range(4)]
        E = sk.entities
        for i in range(4):
            sk.add_constraint("coincident", [E[lines[i]].pts[1], E[lines[(i + 1) % 4]].pts[0]], check=False)
        sk.add_constraint("horizontal", [lines[0]], check=False)
        sk.add_constraint("horizontal", [lines[2]], check=False)
        sk.add_constraint("vertical", [lines[1]], check=False)
        sk.add_constraint("vertical", [lines[3]], check=False)
        if self.center:
            diag = sk.add_line(c[0], c[2], construction=True)
            sk.add_constraint("coincident", [E[diag].pts[0], E[lines[0]].pts[0]], check=False)
            sk.add_constraint("coincident", [E[diag].pts[1], E[lines[2]].pts[0]], check=False)
            cp = sk.add_point(*snaps[0].uv)
            sk.add_constraint("midpoint", [cp, diag], check=False)
            self.attach(cp, snaps[0])
        else:
            self.attach(E[lines[0]].pts[0], snaps[0])
            self.attach(E[lines[2]].pts[0], snaps[1])


class CenterRectTool(RectTool):
    name = "rect_center"
    hint = "Click the center, then a corner."
    center = True


class CircleTool(TwoClickTool):
    name = "circle"
    label = "Circle"
    hint = "Click the center, then the diameter."

    def draw_preview(self, vp, uvs):
        c, p = uvs
        r = math.dist(c, p)
        t = np.linspace(0, 2 * math.pi, 96)
        self.preview(vp, [np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])])
        vp.labels = [(self.fr.to_world(p), "⌀" + format_length(2 * r), THEME.sk_free)]

    def create(self, snaps):
        c, p = snaps[0].uv, snaps[1].uv
        r = math.dist(c, p)
        if r < 1e-6:
            raise ValueError
        cid = self.sk.add_circle(c, r)
        self.attach(self.sk.entities[cid].pts[0], snaps[0])
        if snaps[1].kind in ("point", "curve"):
            # circle through the snapped point
            if snaps[1].kind == "point":
                try:
                    self.sk.add_constraint("coincident", [snaps[1].ref, cid])
                except SketchError:
                    pass


class Arc3Tool(TwoClickTool):
    name = "arc"
    label = "Arc"
    hint = "Click start, end, then a point on the arc."
    clicks_needed = 3

    def draw_preview(self, vp, uvs):
        if len(uvs) == 2:
            self.preview(vp, [uvs])
            return
        arc = _arc_through(*uvs)
        if arc is None:
            self.preview(vp, [uvs[:2]])
            return
        c, r, a0, a1 = arc
        t = np.linspace(a0, a1, 64)
        self.preview(vp, [np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])])
        vp.labels = [(self.fr.to_world(uvs[2]), "R" + format_length(r), THEME.sk_free)]

    def create(self, snaps):
        s, e, m = (sn.uv for sn in snaps)
        arc = _arc_through(s, e, m)
        if arc is None:
            raise ValueError
        c, r, a0, a1 = arc
        ccw = _ccw(s, m, e)
        start, end = (s, e) if ccw else (e, s)
        aid = self.sk.add_arc(c, start, end)
        E = self.sk.entities[aid]
        self.attach(E.pts[1], snaps[0] if ccw else snaps[1])
        self.attach(E.pts[2], snaps[1] if ccw else snaps[0])


def _ccw(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0


def _arc_through(s, e, m):
    ax, ay = s
    bx, by = m
    cx, cy = e
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax ** 2 + ay ** 2) * (by - cy) + (bx ** 2 + by ** 2) * (cy - ay) + (cx ** 2 + cy ** 2) * (ay - by)) / d
    uy = ((ax ** 2 + ay ** 2) * (cx - bx) + (bx ** 2 + by ** 2) * (ax - cx) + (cx ** 2 + cy ** 2) * (bx - ax)) / d
    c = np.array([ux, uy])
    r = math.dist(c, s)
    a_s = math.atan2(ay - uy, ax - ux)
    a_e = math.atan2(cy - uy, cx - ux)
    if _ccw(s, m, e):
        a0, a1 = a_s, a_e
    else:
        a0, a1 = a_e, a_s
    if a1 <= a0:
        a1 += 2 * math.pi
    return c, r, a0, a1


class CenterArcTool(TwoClickTool):
    name = "arc_center"
    label = "Arc"
    hint = "Click the center, the start point, then the end angle."
    clicks_needed = 3

    def draw_preview(self, vp, uvs):
        c = np.asarray(uvs[0])
        r = math.dist(c, uvs[1])
        if len(uvs) == 2:
            self.preview(vp, [[c, uvs[1]]])
            return
        a0 = math.atan2(uvs[1][1] - c[1], uvs[1][0] - c[0])
        a1 = math.atan2(uvs[2][1] - c[1], uvs[2][0] - c[0])
        if a1 <= a0:
            a1 += 2 * math.pi
        t = np.linspace(a0, a1, 64)
        self.preview(vp, [np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])])

    def create(self, snaps):
        c, s, e = (np.asarray(sn.uv) for sn in snaps)
        r = math.dist(c, s)
        a1 = math.atan2(e[1] - c[1], e[0] - c[0])
        end = c + r * np.array([math.cos(a1), math.sin(a1)])
        aid = self.sk.add_arc(c, s, end)
        E = self.sk.entities[aid]
        self.attach(E.pts[0], snaps[0])
        self.attach(E.pts[1], snaps[1])


class PolygonTool(TwoClickTool):
    name = "polygon"
    label = "Polygon"
    hint = "Click center, then a corner. +/- changes the number of sides."
    sides = 6

    def key(self, vp, ev):
        if ev.text() in ("+", "="):
            PolygonTool.sides = min(64, self.sides + 1)
        elif ev.text() == "-":
            PolygonTool.sides = max(3, self.sides - 1)
        else:
            return super().key(vp, ev)
        self.s.message(f"Polygon: {self.sides} sides")
        return True

    def verts(self, c, p):
        c = np.asarray(c)
        r = math.dist(c, p)
        a0 = math.atan2(p[1] - c[1], p[0] - c[0])
        return [c + r * np.array([math.cos(a0 + 2 * math.pi * i / self.sides),
                                  math.sin(a0 + 2 * math.pi * i / self.sides)]) for i in range(self.sides)]

    def draw_preview(self, vp, uvs):
        v = self.verts(*uvs[:2])
        self.preview(vp, [v + [v[0]]])
        vp.labels = [(self.fr.to_world(uvs[1]), f"{self.sides} sides", THEME.sk_free)]

    def create(self, snaps):
        c, p = snaps[0].uv, snaps[1].uv
        if math.dist(c, p) < 1e-6:
            raise ValueError
        v = self.verts(c, p)
        sk = self.sk
        circ = sk.add_circle(c, math.dist(c, p), construction=True)
        lines = [sk.add_line(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]
        E = sk.entities
        for i, l in enumerate(lines):
            sk.add_constraint("coincident", [E[l].pts[1], E[lines[(i + 1) % len(lines)]].pts[0]], check=False)
            sk.add_constraint("coincident", [E[l].pts[0], circ], check=False)
            if i:
                sk.add_constraint("equal", [lines[0], l], check=False)
        self.attach(E[circ].pts[0], snaps[0])


class SlotTool(TwoClickTool):
    name = "slot"
    label = "Slot"
    hint = "Click the two arc centers, then the width."
    clicks_needed = 3

    def geom(self, a, b, w):
        a, b = np.asarray(a), np.asarray(b)
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-9:
            return None
        n = np.array([-d[1], d[0]]) / L
        r = w
        return a, b, n, r

    def draw_preview(self, vp, uvs):
        if len(uvs) == 2:
            self.preview(vp, [uvs])
            return
        a, b = np.asarray(uvs[0]), np.asarray(uvs[1])
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-9:
            return
        n = np.array([-d[1], d[0]]) / L
        r = abs(np.dot(np.asarray(uvs[2]) - a, n))
        ang = math.atan2(n[1], n[0])
        t1 = np.linspace(ang, ang + math.pi, 32)
        t2 = np.linspace(ang + math.pi, ang + 2 * math.pi, 32)
        arc1 = np.column_stack([a[0] + r * np.cos(t1), a[1] + r * np.sin(t1)])
        arc2 = np.column_stack([b[0] + r * np.cos(t2), b[1] + r * np.sin(t2)])
        self.preview(vp, [np.vstack([arc1, arc2, arc1[:1]])])

    def create(self, snaps):
        a, b, w = np.asarray(snaps[0].uv), np.asarray(snaps[1].uv), np.asarray(snaps[2].uv)
        d = b - a
        L = np.linalg.norm(d)
        n = np.array([-d[1], d[0]]) / L
        r = abs(np.dot(w - a, n))
        if r < 1e-6:
            raise ValueError
        sk = self.sk
        p1, p2, p3, p4 = a + n * r, b + n * r, b - n * r, a - n * r
        l1 = sk.add_line(p4, p3)   # bottom a->b
        l2 = sk.add_line(p2, p1)   # top b->a
        arc_b = sk.add_arc(b, p3, p2)
        arc_a = sk.add_arc(a, p1, p4)
        E = sk.entities
        cons = [("coincident", [E[l1].pts[1], E[arc_b].pts[1]]), ("coincident", [E[arc_b].pts[2], E[l2].pts[0]]),
                ("coincident", [E[l2].pts[1], E[arc_a].pts[1]]), ("coincident", [E[arc_a].pts[2], E[l1].pts[0]]),
                ("tangent", [l1, arc_b]), ("tangent", [l2, arc_b]), ("tangent", [l1, arc_a]),
                ("equal", [arc_a, arc_b])]
        for k, refs in cons:
            sk.add_constraint(k, refs, check=False)
        self.attach(E[arc_a].pts[0], snaps[0])
        self.attach(E[arc_b].pts[0], snaps[1])


class SplineTool(SketchTool):
    name = "spline"
    hint = "Click fit points. Double-click or Enter to finish."

    def __init__(self, session):
        super().__init__(session)
        self.pts: list[Snap] = []

    def move(self, vp, x, y, ev):
        sn = self.snap(vp, x, y)
        if sn is None:
            return True
        if self.pts:
            from ..sketch.model import catmull_rom
            self.preview(vp, [catmull_rom(np.array([p.uv for p in self.pts] + [sn.uv]))],
                         [p.uv for p in self.pts])
        else:
            self.snap_marker(vp, sn)
        return True

    def press(self, vp, x, y, ev):
        sn = self.snap(vp, x, y)
        if sn is not None:
            if self.pts and math.dist(self.pts[-1].uv, sn.uv) < 1e-6:
                return True
            self.pts.append(sn)
        return True

    def done(self, vp):
        if len(self.pts) >= 2:
            sid = self.sk.add_spline([p.uv for p in self.pts])
            e = self.sk.entities[sid]
            self.attach(e.pts[0], self.pts[0])
            self.attach(e.pts[-1], self.pts[-1])
            self.sk.solve()
            self.commit("Spline")
        self.pts = []
        vp.tool_lines.clear()
        vp.tool_points.clear()
        self.s.live_update()

    def double_click(self, vp, x, y):
        self.done(vp)
        return True

    def key(self, vp, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.done(vp)
            return True
        return super().key(vp, ev)

    def cancel_step(self, vp):
        if self.pts:
            self.done(vp)
            return True
        return False


class PointTool(SketchTool):
    name = "point"
    hint = "Click to place sketch points."

    def move(self, vp, x, y, ev):
        self.snap_marker(vp, self.snap(vp, x, y))
        return True

    def press(self, vp, x, y, ev):
        sn = self.snap(vp, x, y)
        if sn is None:
            return True
        pid = self.sk.add_point(*sn.uv)
        self.attach(pid, sn)
        self.sk.solve()
        self.commit("Point")
        return True


# ---------------------------------------------------------------------------
class DimensionTool(SketchTool):
    """Smart dimension: click geometry, then place the dimension.

    one line -> length, circle -> diameter, arc -> radius, two points or point
    + line -> distance, two lines -> angle (or distance if parallel).
    """
    name = "dimension"
    hint = "Select geometry to dimension, then click to place."

    def __init__(self, session):
        super().__init__(session)
        self.refs = []

    def _candidate(self, refs):
        sk = self.sk
        kinds = [sk.entities[r].kind for r in refs]
        if len(refs) == 1:
            if kinds[0] == "line":
                return "distance"
            if kinds[0] == "circle":
                return "diameter"
            if kinds[0] == "arc":
                return "radius"
            return None
        if len(refs) == 2:
            if kinds == ["line", "line"]:
                d1, d2 = sk._dir(sk.entities[refs[0]]), sk._dir(sk.entities[refs[1]])
                cross = abs(d1[0] * d2[1] - d1[1] * d2[0]) / (math.hypot(*d1) * math.hypot(*d2) + 1e-12)
                return "distance" if cross < 1e-6 else "angle"
            if set(kinds) <= {"point", "line"}:
                return "distance"
            if kinds == ["point", "point"]:
                return "distance"
        return None

    def press(self, vp, x, y, ev):
        p = vp.pick_at(x, y, {"spoint", "curve", "origin"})
        if p is not None and p.key == self.s.fid:
            r = 0 if p.kind == "origin" else p.index
            ent = self.sk.entities.get(r)
            if ent is not None and r not in self.refs:
                if len(self.refs) == 1 and ent.kind in ("circle", "arc"):
                    self.refs = []
                self.refs.append(r)
                if len(self.refs) > 2:
                    self.refs = self.refs[-1:]
                self.s.highlight([("curve" if ent.kind != "point" else "spoint", r) for r in self.refs])
                if len(self.refs) == 2 or ent.kind in ("circle", "arc"):
                    pass
                return True
        # click on empty space: place the dimension
        if self.refs:
            self.place(vp, x, y)
        return True

    def place(self, vp, x, y):
        kind = self._candidate(self.refs)
        if kind is None:
            self.s.message("Cannot dimension this selection")
            self.refs = []
            self.s.highlight([])
            return
        sk = self.sk
        uv = vp.plane_point(x, y, self.fr)
        # horizontal / vertical distance between two points depending on placement
        if kind == "distance" and len(self.refs) == 2 and all(sk.entities[r].kind == "point" for r in self.refs):
            a, b = np.array(sk.xy(self.refs[0])), np.array(sk.xy(self.refs[1]))
            m = (a + b) / 2
            d = uv - m
            ab = b - a
            if abs(ab[0]) > 1e-9 and abs(ab[1]) > 1e-9:
                if abs(d[1]) > abs(d[0]) * 1.5:
                    kind = "hdistance"
                elif abs(d[0]) > abs(d[1]) * 1.5:
                    kind = "vdistance"
        try:
            val = sk.measure(kind, self.refs)
        except SketchError as exc:
            self.s.message(str(exc))
            self.refs = []
            return
        cid = self.s.add_dimension(kind, list(self.refs), val, uv)
        vp.labels = []
        self.refs = []
        self.s.highlight([])
        if cid is not None:
            self.s.edit_dimension(cid, vp.mapToGlobal(QPointF(x, y).toPoint()))

    def move(self, vp, x, y, ev):
        if self.refs:
            kind = self._candidate(self.refs)
            if kind:
                try:
                    v = self.sk.measure(kind, self.refs)
                    txt = format_angle(v) if kind == "angle" else format_length(v)
                    vp.labels = [(self.fr.to_world(vp.plane_point(x, y, self.fr)), txt, THEME.sk_free)]
                except SketchError:
                    pass
        return False

    def cancel_step(self, vp):
        if self.refs:
            self.refs = []
            self.s.highlight([])
            vp.labels = []
            return True
        return False


# ---------------------------------------------------------------------------
class TrimTool(SketchTool):
    name = "trim"
    hint = "Click a curve segment to remove it up to the nearest intersections."

    def move(self, vp, x, y, ev):
        uv = vp.plane_point(x, y, self.fr)
        p = vp.pick_at(x, y, {"curve"})
        vp.tool_lines.clear()
        if p is not None and p.key == self.s.fid and uv is not None:
            seg = self._segment(p.index, uv)
            if seg is not None:
                vp.tool_lines.add_polyline(self.fr.to_world(seg[0]), (*THEME.sk_origin, 1.0))
        vp.update()
        return False

    def _segment(self, eid, uv):
        sk = self.sk
        e = sk.entities[eid]
        others = [o for o in sk.curves() if o.id != eid]
        cuts = g2.curve_intersections(sk, e, others)
        if e.kind == "line":
            a, b = np.array(sk.xy(e.pts[0])), np.array(sk.xy(e.pts[1]))
            t = g2.seg_param(uv, a, b)
            ts = [0.0] + [c[0] for c in cuts] + [1.0]
            for t0, t1 in zip(ts[:-1], ts[1:]):
                if t0 - 1e-9 <= t <= t1 + 1e-9:
                    return np.array([a + (b - a) * t0, a + (b - a) * t1]), (t0, t1), ts
        elif e.kind in ("circle", "arc"):
            c = np.array(sk.xy(e.pts[0]))
            ang = g2.angle_of(c, uv)
            if e.kind == "circle":
                angs = sorted(set(round(a, 12) for a, _ in cuts))
                if len(angs) < 2:
                    return np.array(sk.polyline(e)), None, None
                for i in range(len(angs)):
                    a0, a1 = angs[i], angs[(i + 1) % len(angs)]
                    if a1 <= a0:
                        a1 += 2 * math.pi
                    if g2.in_arc(ang, a0, a1):
                        t = np.linspace(a0, a1, 48)
                        return np.column_stack([c[0] + e.r * np.cos(t), c[1] + e.r * np.sin(t)]), (a0, a1), angs
            else:
                s0, s1 = sk.arc_angles(e)
                inner = sorted(((a - s0) % (2 * math.pi)) + s0 for a, _ in cuts
                               if g2.in_arc(a, s0, s1) and abs(((a - s0) % (2 * math.pi))) > 1e-9
                               and abs(((a - s0) % (2 * math.pi)) - (s1 - s0)) > 1e-9)
                bounds = [s0] + inner + [s1]
                a = ((ang - s0) % (2 * math.pi)) + s0
                for a0, a1 in zip(bounds[:-1], bounds[1:]):
                    if a0 - 1e-9 <= a <= a1 + 1e-9:
                        t = np.linspace(a0, a1, 48)
                        return np.column_stack([c[0] + e.r * np.cos(t), c[1] + e.r * np.sin(t)]), (a0, a1), bounds
        return None

    def press(self, vp, x, y, ev):
        uv = vp.plane_point(x, y, self.fr)
        p = vp.pick_at(x, y, {"curve"})
        if p is None or p.key != self.s.fid or uv is None:
            return True
        seg = self._segment(p.index, uv)
        if seg is None:
            return True
        sk = self.sk
        e = sk.entities[p.index]
        _, rng, allb = seg
        constr = e.construction
        if e.kind == "line":
            a, b = np.array(sk.xy(e.pts[0])), np.array(sk.xy(e.pts[1]))
            t0, t1 = rng
            keep = []
            if t0 > 1e-9:
                keep.append((a, a + (b - a) * t0))
            if t1 < 1 - 1e-9:
                keep.append((a + (b - a) * t1, b))
            self._replace(e, [("line", k) for k in keep], constr)
        elif e.kind == "circle":
            if rng is None:
                sk.remove(e.id)
            else:
                c = np.array(sk.xy(e.pts[0]))
                a0, a1 = rng
                # keep the complementary arc a1 -> a0 + 2pi
                s = c + e.r * np.array([math.cos(a1), math.sin(a1)])
                t = c + e.r * np.array([math.cos(a0), math.sin(a0)])
                self._replace(e, [("arc", (c, s, t))], constr)
        elif e.kind == "arc":
            c = np.array(sk.xy(e.pts[0]))
            s0, s1 = sk.arc_angles(e)
            a0, a1 = rng
            keep = []
            P = lambda a: c + e.r * np.array([math.cos(a), math.sin(a)])  # noqa: E731
            if a0 > s0 + 1e-9:
                keep.append(("arc", (c, P(s0), P(a0))))
            if a1 < s1 - 1e-9:
                keep.append(("arc", (c, P(a1), P(s1))))
            self._replace(e, keep, constr)
        sk.solve()
        self.commit("Trim")
        vp.tool_lines.clear()
        return True

    def _replace(self, e, parts, construction):
        """Replace a curve with trimmed parts; re-attach endpoint coincidences."""
        sk = self.sk
        old_pts = {pid: np.array(sk.xy(pid)) for pid in e.pts}
        links = []  # (old point id, other ref) from coincident constraints
        for c in list(sk.constraints.values()):
            if c.kind == "coincident" and set(c.refs) & set(e.pts):
                other = [r for r in c.refs if r not in e.pts]
                mine = [r for r in c.refs if r in e.pts]
                if other and mine:
                    links.append((mine[0], other[0]))
        sk.remove(e.id)
        new_pts = []
        for kind, geom in parts:
            if kind == "line":
                nid = sk.add_line(*geom, construction=construction)
            else:
                nid = sk.add_arc(*geom, construction=construction)
            ne = sk.entities[nid]
            new_pts += ne.pts[1:] if kind == "arc" else ne.pts
        for old, other in links:
            if other not in sk.entities:
                continue
            for np_id in new_pts:
                if math.dist(sk.xy(np_id), old_pts[old]) < 1e-6:
                    try:
                        sk.add_constraint("coincident", [np_id, other], check=False)
                    except SketchError:
                        pass
        # Endpoints created at intersections lie on the cutting curves
        for np_id in new_pts:
            p = np.array(sk.xy(np_id))
            if any(math.dist(p, q) < 1e-6 for q in old_pts.values()):
                continue
            for o in sk.curves():
                if np_id in o.pts:
                    continue
                q, d = g2.nearest_on_curve(sk, o, p)
                if d < 1e-6 and o.kind != "spline":
                    target = next((pid for pid in o.pts if math.dist(sk.xy(pid), p) < 1e-6), None)
                    try:
                        sk.add_constraint("coincident", [np_id, target if target is not None else o.id], check=False)
                    except SketchError:
                        pass
                    break


class SketchFilletTool(SketchTool):
    name = "sketch_fillet"
    hint = "Click near a corner between two lines."
    radius = 5.0

    def press(self, vp, x, y, ev):
        uv = vp.plane_point(x, y, self.fr)
        if uv is None:
            return True
        sk = self.sk
        tol = 25 * self.px(vp)
        # find two lines meeting at a coincident corner near the click
        best = None
        for c in sk.constraints.values():
            if c.kind != "coincident":
                continue
            a, b = c.refs
            la = next((e for e in sk.curves() if a in e.pts and e.kind == "line"), None)
            lb = next((e for e in sk.curves() if b in e.pts and e.kind == "line"), None)
            if la is None or lb is None or la.id == lb.id:
                continue
            d = math.dist(sk.xy(a), uv)
            if d < tol and (best is None or d < best[0]):
                best = (d, la, a, lb, b)
        if best is None:
            self.s.message("Click near a corner where two lines meet")
            return True
        _, la, pa, lb, pb = best
        from PySide6.QtWidgets import QInputDialog
        r, ok = QInputDialog.getDouble(vp, "Sketch Fillet", "Radius (mm):", self.radius, 0.001, 1e6, 3)
        if not ok:
            return True
        SketchFilletTool.radius = r
        try:
            fillet_corner(sk, la, pa, lb, pb, r)
            sk.solve()
            self.commit("Sketch Fillet")
        except (SketchError, ValueError) as exc:
            self.s.message(f"Fillet failed: {exc}")
        return True


def fillet_corner(sk, la, pa, lb, pb, r):
    corner = np.array(sk.xy(pa))
    oa = np.array(sk.xy(la.pts[1] if la.pts[0] == pa else la.pts[0]))
    ob = np.array(sk.xy(lb.pts[1] if lb.pts[0] == pb else lb.pts[0]))
    da = (oa - corner) / np.linalg.norm(oa - corner)
    db = (ob - corner) / np.linalg.norm(ob - corner)
    ang = math.acos(max(-1, min(1, float(np.dot(da, db)))))
    if ang < 1e-3 or ang > math.pi - 1e-3:
        raise ValueError("lines are parallel")
    t = r / math.tan(ang / 2)
    if t >= math.dist(corner, oa) or t >= math.dist(corner, ob):
        raise ValueError("radius too large")
    ta, tb = corner + da * t, corner + db * t
    bis = (da + db) / np.linalg.norm(da + db)
    center = corner + bis * (r / math.sin(ang / 2))
    # remove the corner coincidence, move endpoints, add arc
    for cid in [cid for cid, c in sk.constraints.items() if c.kind == "coincident" and set(c.refs) == {pa, pb}]:
        del sk.constraints[cid]
    sk.entities[pa].x, sk.entities[pa].y = ta
    sk.entities[pb].x, sk.entities[pb].y = tb
    cross = da[0] * db[1] - da[1] * db[0]
    s, e = (ta, tb) if cross < 0 else (tb, ta)
    aid = sk.add_arc(center, s, e)
    E = sk.entities[aid]
    sp, ep = (pa, pb) if cross < 0 else (pb, pa)
    sk.add_constraint("coincident", [E.pts[1], sp], check=False)
    sk.add_constraint("coincident", [E.pts[2], ep], check=False)
    sk.add_constraint("tangent", [la.id, aid], check=False)
    sk.add_constraint("tangent", [lb.id, aid], check=False)
    return aid


class ProjectTool(SketchTool):
    """Project body edges / vertices onto the sketch plane as fixed geometry."""
    name = "project"
    hint = "Click body edges or vertices to project them into the sketch."

    def press(self, vp, x, y, ev):
        p = vp.pick_at(x, y, {"edge", "vertex"})
        if p is None:
            return True
        doc = self.s.doc
        body = doc.state.bodies.get(p.key)
        if body is None:
            return True
        sk, fr = self.sk, self.fr
        if p.kind == "vertex":
            v = K.vertex_point(K.vertices(body.shape)[p.index])
            pid = sk.add_point(*fr.to_local(v))
            sk.entities[pid].fixed = True
        else:
            edge = K.edges(body.shape)[p.index]
            info = K.edge_info(edge)
            if info["type"] == "line":
                a, b = fr.to_local(info["start"]), fr.to_local(info["end"])
                if math.dist(a, b) < 1e-6:
                    self.s.message("Edge is perpendicular to the sketch plane")
                    return True
                lid = sk.add_line(a, b)
                for pid in sk.entities[lid].pts:
                    sk.entities[pid].fixed = True
            elif info["type"] == "circle" and abs(abs(np.dot(info["axis"], fr.normal)) - 1) < 1e-6:
                c = fr.to_local(info["center"])
                if math.dist(info["start"], info["end"]) < 1e-6:
                    cid = sk.add_circle(c, info["radius"])
                    sk.add_constraint("fix", [cid], check=False)
                else:
                    s, e = fr.to_local(info["start"]), fr.to_local(info["end"])
                    mid = fr.to_local(info["mid"])
                    arc = _arc_through(s, e, mid)
                    if arc is None:
                        return True
                    st, en = (s, e) if _ccw(s, mid, e) else (e, s)
                    aid = sk.add_arc(c, st, en)
                    sk.add_constraint("fix", [aid], check=False)
            else:
                # general curve: sample as fixed spline
                pts = K.edge_polyline(edge, 0.05)
                uv = fr.to_local(pts)
                if len(uv) > 2:
                    idx = np.linspace(0, len(uv) - 1, min(12, len(uv))).astype(int)
                    sid = sk.add_spline(uv[idx])
                    for pid in sk.entities[sid].pts:
                        sk.entities[pid].fixed = True
        sk.solve()
        self.commit("Project")
        return True


TOOLS = {
    "line": LineTool, "rect": RectTool, "rect_center": CenterRectTool, "circle": CircleTool,
    "arc": Arc3Tool, "arc_center": CenterArcTool, "polygon": PolygonTool, "slot": SlotTool,
    "spline": SplineTool, "point": PointTool, "dimension": DimensionTool, "trim": TrimTool,
    "sketch_fillet": SketchFilletTool, "project": ProjectTool,
}


def paint_hint(p, vp, text):
    p.setPen(QPen(QColor(40, 44, 52) if THEME.light else QColor(220, 222, 228)))
    p.drawText(12, 22, text)
