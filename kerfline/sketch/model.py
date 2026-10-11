"""Sketch data model: points, curves, constraints and dimensions.

A :class:`Sketch` lives on a plane (origin + x/y axes in 3D).  All sketch
geometry is stored in 2D plane coordinates (mm).  Dimensions refer to named
parameters in the document's :class:`ParameterTable` so they participate in
the parametric model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import solver as S

ORIGIN_ID = 0

CURVE_KINDS = ("line", "circle", "arc", "spline", "ellipse", "text")

DIMENSION_KINDS = {"distance": "length", "hdistance": "length", "vdistance": "length",
                   "radius": "length", "diameter": "length", "angle": "angle"}

CONSTRAINT_LABELS = {
    "coincident": "Coincident", "horizontal": "Horizontal", "vertical": "Vertical",
    "parallel": "Parallel", "perpendicular": "Perpendicular", "collinear": "Collinear",
    "tangent": "Tangent", "equal": "Equal", "concentric": "Concentric",
    "midpoint": "Midpoint", "symmetric": "Symmetry", "fix": "Fix/Unfix",
    "distance": "Distance", "hdistance": "Horizontal distance", "vdistance": "Vertical distance",
    "radius": "Radius", "diameter": "Diameter", "angle": "Angle",
}


class SketchError(Exception):
    pass


@dataclass
class Entity:
    id: int
    kind: str                         # point | line | circle | arc | spline
    pts: list[int] = field(default_factory=list)  # point ids (curves)
    x: float = 0.0                    # point coords (kind == point)
    y: float = 0.0
    r: float = 0.0                    # circle / arc radius
    construction: bool = False
    fixed: bool = False               # origin / projected reference geometry
    owner: int | None = None          # for points: curve that created them
    text: str = ""                    # kind == text
    height: float = 5.0               # text font height (mm)
    font: str = "sans"
    bold: bool = False
    italic: bool = False
    angle: float = 0.0                # text rotation (rad)

    def to_dict(self):
        d = {"id": self.id, "kind": self.kind}
        if self.kind == "point":
            d.update(x=self.x, y=self.y)
            if self.owner is not None:
                d["owner"] = self.owner
        else:
            d["pts"] = list(self.pts)
        if self.kind in ("circle", "arc", "ellipse"):
            d["r"] = self.r
        if self.kind == "text":
            d.update(text=self.text, height=self.height, font=self.font, angle=self.angle)
            if self.bold:
                d["bold"] = True
            if self.italic:
                d["italic"] = True
        if self.construction:
            d["construction"] = True
        if self.fixed:
            d["fixed"] = True
        return d

    @staticmethod
    def from_dict(d):
        return Entity(d["id"], d["kind"], list(d.get("pts", [])), d.get("x", 0.0), d.get("y", 0.0),
                      d.get("r", 0.0), d.get("construction", False), d.get("fixed", False), d.get("owner"),
                      d.get("text", ""), d.get("height", 5.0), d.get("font", "sans"), d.get("bold", False),
                      d.get("italic", False), d.get("angle", 0.0))


@dataclass
class Constraint:
    id: int
    kind: str
    refs: list[int]
    param: str | None = None          # dimension parameter name
    data: dict = field(default_factory=dict)  # sign flags, fix coords, label offset
    driven: bool = False              # reference (driven) dimension

    def to_dict(self):
        d = {"id": self.id, "kind": self.kind, "refs": list(self.refs)}
        if self.param:
            d["param"] = self.param
        if self.data:
            d["data"] = dict(self.data)
        if self.driven:
            d["driven"] = True
        return d

    @staticmethod
    def from_dict(d):
        return Constraint(d["id"], d["kind"], list(d["refs"]), d.get("param"), dict(d.get("data", {})),
                          d.get("driven", False))


class Sketch:
    def __init__(self):
        self.entities: dict[int, Entity] = {}
        self.constraints: dict[int, Constraint] = {}
        self._next = 1
        self.entities[ORIGIN_ID] = Entity(ORIGIN_ID, "point", fixed=True)
        self.param_value = lambda name: 0.0   # injected by the document
        self.dof = 0
        self.constrained: set[int] = set()   # fully constrained entity ids
        self.last_ok = True

    # ------------------------------------------------------------------ ids
    def _nid(self) -> int:
        i = self._next
        self._next += 1
        return i

    # ------------------------------------------------------------------ creation
    def add_point(self, x, y, owner=None, construction=False) -> int:
        i = self._nid()
        self.entities[i] = Entity(i, "point", x=float(x), y=float(y), owner=owner, construction=construction)
        return i

    def _pt(self, p, owner):
        """Accept a point id or an (x, y) tuple."""
        if isinstance(p, (int, np.integer)):
            return int(p)
        return self.add_point(p[0], p[1], owner=owner)

    def add_line(self, a, b, construction=False) -> int:
        i = self._nid()
        e = Entity(i, "line", construction=construction)
        self.entities[i] = e
        e.pts = [self._pt(a, i), self._pt(b, i)]
        return i

    def add_circle(self, c, r, construction=False) -> int:
        i = self._nid()
        e = Entity(i, "circle", r=float(r), construction=construction)
        self.entities[i] = e
        e.pts = [self._pt(c, i)]
        return i

    def add_arc(self, c, s, e_, construction=False) -> int:
        """Counter-clockwise arc from ``s`` to ``e_`` about centre ``c``."""
        i = self._nid()
        e = Entity(i, "arc", construction=construction)
        self.entities[i] = e
        e.pts = [self._pt(c, i), self._pt(s, i), self._pt(e_, i)]
        cp, sp = self.xy(e.pts[0]), self.xy(e.pts[1])
        e.r = math.hypot(sp[0] - cp[0], sp[1] - cp[1])
        return i

    def add_spline(self, pts, construction=False) -> int:
        i = self._nid()
        e = Entity(i, "spline", construction=construction)
        self.entities[i] = e
        e.pts = [self._pt(p, i) for p in pts]
        return i

    def add_ellipse(self, center, major_end, minor_r, construction=False) -> int:
        """Ellipse given by centre, end of the major axis and minor radius."""
        i = self._nid()
        e = Entity(i, "ellipse", r=float(minor_r), construction=construction)
        self.entities[i] = e
        e.pts = [self._pt(center, i), self._pt(major_end, i)]
        return i

    def add_text(self, anchor, text, height=5.0, font="sans", bold=False, italic=False, angle=0.0,
                 construction=False) -> int:
        i = self._nid()
        e = Entity(i, "text", construction=construction, text=text, height=float(height), font=font, bold=bold,
                   italic=italic, angle=float(angle))
        self.entities[i] = e
        e.pts = [self._pt(anchor, i)]
        return i

    def add_constraint(self, kind, refs, param=None, data=None, driven=False, check=True) -> int:
        i = self._nid()
        c = Constraint(i, kind, [int(r) for r in refs], param, dict(data or {}), driven)
        self._init_constraint_data(c)
        self.constraints[i] = c
        if check and not driven:
            before_rank = getattr(self, "_rank", None)
            res = self.solve()
            if not res.ok or (res.redundant and before_rank is not None and res.rank == before_rank):
                del self.constraints[i]
                self.solve()
                raise SketchError("Constraint would over-constrain the sketch")
        return i

    def _init_constraint_data(self, c: Constraint):
        """Capture branch choices (signs) from current geometry so the solver
        keeps the configuration the user sees."""
        if c.kind == "tangent":
            a, b = (self.entities[r] for r in c.refs)
            if a.kind in ("circle", "arc") and b.kind == "line":
                c.refs = [b.id, a.id]
                a, b = b, a
            if a.kind == "line":
                p, q = self.xy(a.pts[0]), self.xy(a.pts[1])
                cc = self.xy(b.pts[0])
                d = S.r_point_on_line((cc[0], cc[1], p[0], p[1], q[0], q[1]))
                c.data.setdefault("sign", 1.0 if d >= 0 else -1.0)
            else:
                c1, c2 = self.xy(a.pts[0]), self.xy(b.pts[0])
                d = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
                c.data.setdefault("internal", d < max(a.r, b.r))
        if c.kind == "angle":
            l1, l2 = (self.entities[r] for r in c.refs)
            d1 = self._dir(l1)
            d2 = self._dir(l2)
            a = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
            c.data.setdefault("sign", 1.0 if a >= 0 else -1.0)
        if c.kind == "fix":
            e = self.entities[c.refs[0]]
            pts = [e.id] if e.kind == "point" else e.pts
            c.data.setdefault("xy", [list(self.xy(p)) for p in pts])
            if e.kind in ("circle", "arc"):
                c.data.setdefault("r", e.r)

    def _dir(self, line):
        p, q = self.xy(line.pts[0]), self.xy(line.pts[1])
        return (q[0] - p[0], q[1] - p[1])

    # ------------------------------------------------------------------ queries
    def xy(self, pid) -> tuple[float, float]:
        e = self.entities[pid]
        return (e.x, e.y)

    def points(self):
        return [e for e in self.entities.values() if e.kind == "point"]

    def curves(self, include_construction=True):
        return [e for e in self.entities.values() if e.kind in CURVE_KINDS
                and (include_construction or not e.construction)]

    def remove(self, eid: int) -> None:
        """Delete an entity (and dependent points/constraints) or a constraint."""
        if eid in self.constraints:
            del self.constraints[eid]
            return
        e = self.entities.get(eid)
        if e is None or eid == ORIGIN_ID or e.fixed:
            return
        doomed = {eid}
        if e.kind != "point":
            for p in e.pts:
                # keep points that are shared with other curves via coincidence? Points are
                # owned by exactly one curve; shared positions use coincident constraints.
                if self.entities[p].owner == eid:
                    doomed.add(p)
        else:
            # deleting a curve's endpoint deletes the curve
            for c in self.curves():
                if eid in c.pts:
                    doomed.add(c.id)
                    doomed.update(p for p in c.pts if self.entities[p].owner == c.id)
        for d in doomed:
            self.entities.pop(d, None)
        for cid in [cid for cid, c in self.constraints.items() if doomed & set(c.refs)]:
            del self.constraints[cid]

    def dimension_params(self) -> list[str]:
        return [c.param for c in self.constraints.values() if c.param]

    # ------------------------------------------------------------------ solving
    def _build(self):
        """Create variable vector + equations from current state."""
        index: dict[tuple[int, str], int] = {}
        x0: list[float] = []

        def var(eid, comp, val):
            key = (eid, comp)
            if key not in index:
                index[key] = len(x0)
                x0.append(val)
            return index[key]

        eqs: list[S.Equation] = []
        pinned = []
        for e in self.entities.values():
            if e.kind == "point":
                ix, iy = var(e.id, "x", e.x), var(e.id, "y", e.y)
                if e.fixed:
                    pinned.append(S.Equation([ix, iy], S.make_fix(e.x, e.y), 2, ("fixed", e.id)))
        for e in self.entities.values():
            if e.kind in ("circle", "arc"):
                var(e.id, "r", e.r)
            if e.kind == "arc":
                c, s, t = e.pts
                ir = index[(e.id, "r")]
                # r_point_on_circle expects (px, py, cx, cy, r)
                for p in (s, t):
                    eqs.append(S.Equation(self._pv(index, p) + self._pv(index, c) + [ir],
                                          S.r_point_on_circle, 1, ("arc", e.id)))

        for c in self.constraints.values():
            if c.driven:
                continue
            try:
                eqs.extend(self._equations(c, index))
            except KeyError:
                continue  # dangling reference; ignored
        return index, np.array(x0, float), pinned + eqs

    @staticmethod
    def _pv(index, pid):
        return [index[(pid, "x")], index[(pid, "y")]]

    def _lv(self, index, lid):
        e = self.entities[lid]
        return self._pv(index, e.pts[0]) + self._pv(index, e.pts[1])

    def _cv(self, index, cid):  # centre + radius
        e = self.entities[cid]
        return self._pv(index, e.pts[0]) + [index[(cid, "r")]]

    def _equations(self, c: Constraint, index) -> list[S.Equation]:
        E = self.entities
        k, refs = c.kind, c.refs
        val = (lambda: self.param_value(c.param)) if c.param else (lambda: 0.0)
        eq = lambda v, f, n=1: S.Equation(v, f, n, c.id)  # noqa: E731
        kinds = [E[r].kind for r in refs]

        if k == "coincident":
            a, b = refs
            if kinds[0] != "point":
                a, b = b, a
                kinds = kinds[::-1]
            if kinds[1] == "point":
                return [eq(self._pv(index, a) + self._pv(index, b), S.r_coincident, 2)]
            if kinds[1] == "line":
                return [eq(self._pv(index, a) + self._lv(index, b), S.r_point_on_line)]
            if kinds[1] in ("circle", "arc"):
                return [eq(self._pv(index, a) + self._cv(index, b), S.r_point_on_circle)]
            if kinds[1] == "spline":
                return []
        if k in ("horizontal", "vertical"):
            f = S.r_horizontal if k == "horizontal" else S.r_vertical
            if kinds[0] == "line":
                return [eq(self._lv(index, refs[0]), f)]
            return [eq(self._pv(index, refs[0]) + self._pv(index, refs[1]), f)]
        if k == "parallel":
            return [eq(self._lv(index, refs[0]) + self._lv(index, refs[1]), S.r_parallel)]
        if k == "perpendicular":
            return [eq(self._lv(index, refs[0]) + self._lv(index, refs[1]), S.r_perpendicular)]
        if k == "collinear":
            l2 = E[refs[1]]
            v1 = self._lv(index, refs[0])
            return [eq(self._pv(index, l2.pts[0]) + v1, S.r_point_on_line),
                    eq(self._pv(index, l2.pts[1]) + v1, S.r_point_on_line)]
        if k == "equal":
            if kinds[0] == "line":
                return [eq(self._lv(index, refs[0]) + self._lv(index, refs[1]), S.r_equal_length)]
            return [eq([index[(refs[0], "r")], index[(refs[1], "r")]], S.r_equal)]
        if k == "concentric":
            return [eq(self._pv(index, E[refs[0]].pts[0]) + self._pv(index, E[refs[1]].pts[0]), S.r_coincident, 2)]
        if k == "tangent":
            if kinds[0] == "line":
                return [eq(self._lv(index, refs[0]) + self._cv(index, refs[1]),
                           S.make_tangent_line_circle(c.data.get("sign", 1.0)))]
            return [eq(self._cv(index, refs[0]) + self._cv(index, refs[1]),
                       S.make_tangent_circle_circle(c.data.get("internal", False)))]
        if k == "midpoint":
            p, l = refs if kinds[0] == "point" else refs[::-1]
            return [eq(self._pv(index, p) + self._lv(index, l), S.r_midpoint, 2)]
        if k == "symmetric":
            return [eq(self._pv(index, refs[0]) + self._pv(index, refs[1]) + self._lv(index, refs[2]), S.r_symmetric, 2)]
        if k == "fix":
            e = E[refs[0]]
            pts = [e.id] if e.kind == "point" else e.pts
            out = [eq(self._pv(index, p), S.make_fix(*xy), 2) for p, xy in zip(pts, c.data["xy"])]
            if e.kind in ("circle", "arc") and "r" in c.data:
                r0 = c.data["r"]
                out.append(eq([index[(e.id, "r")]], S.make_value(lambda: r0)))
            return out
        # ---- dimensions
        if k == "distance":
            if len(refs) == 1:  # line length
                return [eq(self._lv(index, refs[0]), S.make_distance(val))]
            if kinds == ["point", "point"]:
                return [eq(self._pv(index, refs[0]) + self._pv(index, refs[1]), S.make_distance(val))]
            p, l = (refs if kinds[0] == "point" else refs[::-1])
            if E[l].kind == "line" and E[p].kind == "point":
                return [eq(self._pv(index, p) + self._lv(index, l), S.make_point_line_distance(val))]
            if kinds == ["line", "line"]:  # parallel-line distance: from l2.p0 to l1
                return [eq(self._pv(index, E[refs[1]].pts[0]) + self._lv(index, refs[0]),
                           S.make_point_line_distance(val))]
        if k in ("hdistance", "vdistance"):
            f = S.make_hdistance(val) if k == "hdistance" else S.make_vdistance(val)
            if len(refs) == 1:
                return [eq(self._lv(index, refs[0]), f)]
            return [eq(self._pv(index, refs[0]) + self._pv(index, refs[1]), f)]
        if k == "radius":
            return [eq([index[(refs[0], "r")]], S.make_value(val))]
        if k == "diameter":
            return [eq([index[(refs[0], "r")]], S.make_value(val, 2.0))]
        if k == "angle":
            return [eq(self._lv(index, refs[0]) + self._lv(index, refs[1]),
                       S.make_angle(val, c.data.get("sign", 1.0)))]
        raise SketchError(f"unsupported constraint '{k}' on {kinds}")

    def solve(self, drag: dict[int, tuple[float, float]] | None = None, analyse: bool = True):
        """Solve the sketch.  ``drag`` maps point ids to target positions."""
        index, x0, eqs = self._build()
        weights = np.ones(len(x0))
        if drag:
            for pid, (tx, ty) in drag.items():
                if (pid, "x") in index:
                    ix, iy = index[(pid, "x")], index[(pid, "y")]
                    x0[ix], x0[iy] = tx, ty
                    weights[ix] = weights[iy] = 1e-3
        x, res = S.solve(eqs, x0, weights, analyse=analyse)
        if not res.ok and drag:
            # The drag target is unreachable: fall back to the closest reachable state
            index, x0b, eqs = self._build()
            x, res = S.solve(eqs, x0b, analyse=analyse)
        for (eid, comp), i in index.items():
            setattr(self.entities[eid], comp, float(x[i]))
        self.last_ok = res.ok
        if analyse:
            self.dof = res.dof
            self._rank = res.rank
            free_ids = {eid for (eid, _), i in index.items() if res.free_vars[i]}
            self.constrained = set()
            for e in self.entities.values():
                ids = {e.id} if e.kind == "point" else set(e.pts) | {e.id}
                if not (ids & free_ids):
                    self.constrained.add(e.id)
        return res

    # ------------------------------------------------------------------ measurement helpers
    def measure(self, kind: str, refs: list[int]) -> float:
        """Current geometric value for a prospective dimension (mm / rad)."""
        E = self.entities
        kinds = [E[r].kind for r in refs]
        if kind in ("radius", "diameter"):
            return E[refs[0]].r * (2 if kind == "diameter" else 1)
        if kind == "angle":
            d1, d2 = self._dir(E[refs[0]]), self._dir(E[refs[1]])
            a = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
            return abs(a)
        if len(refs) == 1:
            p, q = (self.xy(i) for i in E[refs[0]].pts)
        elif kinds == ["point", "point"]:
            p, q = self.xy(refs[0]), self.xy(refs[1])
        elif "line" in kinds and "point" in kinds:
            pid, lid = (refs if kinds[0] == "point" else refs[::-1])
            a, b = (self.xy(i) for i in E[lid].pts)
            pp = self.xy(pid)
            return abs(S.r_point_on_line((*pp, *a, *b)))
        elif kinds == ["line", "line"]:
            a, b = (self.xy(i) for i in E[refs[0]].pts)
            pp = self.xy(E[refs[1]].pts[0])
            return abs(S.r_point_on_line((*pp, *a, *b)))
        else:
            raise SketchError("cannot dimension this selection")
        if kind == "hdistance":
            return abs(q[0] - p[0])
        if kind == "vdistance":
            return abs(q[1] - p[1])
        return math.hypot(q[0] - p[0], q[1] - p[1])

    # ------------------------------------------------------------------ geometry export
    def arc_angles(self, e: Entity):
        c, s, t = (self.xy(i) for i in e.pts)
        a0 = math.atan2(s[1] - c[1], s[0] - c[0])
        a1 = math.atan2(t[1] - c[1], t[0] - c[0])
        if a1 <= a0:
            a1 += 2 * math.pi
        return a0, a1

    def polylines(self, e: Entity, seg_len: float = 1.0) -> list[np.ndarray]:
        """Display polylines for a curve (text has one per glyph outline edge)."""
        if e.kind == "text":
            return text_outlines(self, e)
        pl = self.polyline(e, seg_len)
        return [pl] if len(pl) else []

    def polyline(self, e: Entity, seg_len: float = 1.0) -> np.ndarray:
        """Discretised curve for display (Nx2)."""
        if e.kind == "line":
            return np.array([self.xy(e.pts[0]), self.xy(e.pts[1])])
        if e.kind == "circle":
            c = self.xy(e.pts[0])
            n = max(32, min(256, int(2 * math.pi * e.r / max(seg_len, 1e-6))))
            t = np.linspace(0, 2 * math.pi, n + 1)
            return np.column_stack([c[0] + e.r * np.cos(t), c[1] + e.r * np.sin(t)])
        if e.kind == "arc":
            c = self.xy(e.pts[0])
            a0, a1 = self.arc_angles(e)
            n = max(8, min(256, int((a1 - a0) * e.r / max(seg_len, 1e-6))))
            t = np.linspace(a0, a1, n + 1)
            return np.column_stack([c[0] + e.r * np.cos(t), c[1] + e.r * np.sin(t)])
        if e.kind == "spline":
            return catmull_rom(np.array([self.xy(p) for p in e.pts]))
        if e.kind == "ellipse":
            c, m = np.array(self.xy(e.pts[0])), np.array(self.xy(e.pts[1]))
            a = float(np.linalg.norm(m - c))
            if a < 1e-9:
                return np.zeros((0, 2))
            u = (m - c) / a
            v = np.array([-u[1], u[0]])
            t = np.linspace(0, 2 * math.pi, 129)
            return c + np.outer(a * np.cos(t), u) + np.outer(e.r * np.sin(t), v)
        if e.kind == "text":
            pls = text_outlines(self, e)
            return np.vstack(pls) if pls else np.zeros((0, 2))
        return np.zeros((0, 2))

    # ------------------------------------------------------------------ serialisation
    def to_dict(self):
        return {"next": self._next,
                "entities": [e.to_dict() for e in self.entities.values()],
                "constraints": [c.to_dict() for c in self.constraints.values()]}

    @staticmethod
    def from_dict(d) -> "Sketch":
        s = Sketch()
        s.entities = {}
        for ed in d["entities"]:
            e = Entity.from_dict(ed)
            s.entities[e.id] = e
        if ORIGIN_ID not in s.entities:
            s.entities[ORIGIN_ID] = Entity(ORIGIN_ID, "point", fixed=True)
        s.constraints = {cd["id"]: Constraint.from_dict(cd) for cd in d.get("constraints", [])}
        s._next = d.get("next", max(list(s.entities) + list(s.constraints) + [0]) + 1)
        return s

    def copy(self) -> "Sketch":
        s = Sketch.from_dict(self.to_dict())
        s.param_value = self.param_value
        return s


_TEXT_OUTLINE_CACHE: dict = {}


def text_outlines(sk, e: Entity) -> list[np.ndarray]:
    """2D outline polylines of a text entity (cached per text/height/font)."""
    from ..core import kernel as K
    key = (e.text, round(e.height, 6), e.font, e.bold, e.italic)
    base = _TEXT_OUTLINE_CACHE.get(key)
    if base is None:
        try:
            shp = K.text_shape(e.text, e.height, e.font, e.bold, e.italic)
            base = [K.edge_polyline(ed, max(e.height * 0.01, 0.01))[:, :2].astype(float) for ed in K.edges(shp)]
        except Exception:
            base = []
        if len(_TEXT_OUTLINE_CACHE) > 128:
            _TEXT_OUTLINE_CACHE.clear()
        _TEXT_OUTLINE_CACHE[key] = base
    a = np.array(sk.xy(e.pts[0]))
    ca, sa = math.cos(e.angle), math.sin(e.angle)
    R = np.array([[ca, -sa], [sa, ca]])
    return [pl @ R.T + a for pl in base]


def catmull_rom(P: np.ndarray, samples: int = 16) -> np.ndarray:
    """Preview polyline for an interpolating spline (the exact B-spline is
    built by the kernel; this is only for fast display while sketching)."""
    if len(P) < 3:
        return P
    pts = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        t = np.linspace(0, 1, samples, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1:])
    return np.vstack(out)
