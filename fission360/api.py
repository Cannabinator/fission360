"""Scripting API.

The API drives the *same* document model as the GUI: every call adds a real
feature to the parametric timeline (with parameters, undo and rebuild), so a
script's result can be edited in the application afterwards.

    from fission360.api import Design

    d = Design()
    d.param("width", "60 mm")
    sk = d.sketch("XY")
    sk.rect(0, 0, "width", 40)            # dimensions accept expressions
    sk.circle(30, 20, 8)
    base = d.extrude(sk.profile(5, 5), "12 mm")          # join/cut chosen automatically
    d.fillet(base.edges(direction=(0, 0, 1)), "2 mm")     # select by geometry
    d.hole(base.face(normal=(0, 0, 1)), at=(10, 10), diameter="5 mm", depth="8 mm")
    d.save("part.f3x"); d.export("part.step")

Run a script headless with ``fission360 --run script.py [file.f3x]`` or from
the GUI via Tools > Run Script (the script sees ``design`` bound to the open document).
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .core import kernel as K
from .core import references as R
from .core.document import Document
from .core.features import default_data
from .sketch.model import Sketch


class DesignError(Exception):
    pass


def _is_expr(v) -> bool:
    return isinstance(v, str)


class Selection:
    """Geometry of one body, filtered by simple predicates."""

    def __init__(self, design: "Design", body_id: str):
        self.d, self.body_id = design, body_id

    @property
    def shape(self):
        return self.d.doc.state.bodies[self.body_id].shape

    # ---- faces / edges selected by geometry, returned as persistent references
    def faces(self, normal=None, type=None, min_area=None, at_z=None, tol=1e-3) -> list[dict]:
        out = []
        for f in K.faces(self.shape):
            i = K.face_info(f)
            if type and i["type"] != type:
                continue
            if normal is not None:
                n = np.asarray(normal, float)
                n /= np.linalg.norm(n)
                if np.dot(i["normal"], n) < 1 - 1e-3:
                    continue
            if min_area is not None and i["area"] < min_area:
                continue
            if at_z is not None and abs(i["center"][2] - at_z) > tol:
                continue
            out.append({"face": R.face_ref(self.body_id, f)})
        return out

    def face(self, **kw) -> dict:
        r = self.faces(**kw)
        if not r:
            raise DesignError(f"no face matches {kw}")
        # largest matching face
        return r[0]

    def edges(self, direction=None, type=None, min_length=None, on_face: dict | None = None) -> list[dict]:
        pool = K.edges(self.shape)
        if on_face is not None:
            _, face = R.resolve_face(self.d.doc.state, on_face["face"])
            pool = K.edges(face)
        out = []
        for e in pool:
            i = K.edge_info(e)
            if type and i["type"] != type:
                continue
            if direction is not None:
                dv = np.asarray(direction, float)
                dv /= np.linalg.norm(dv)
                if abs(np.dot(i["tangent"], dv)) < 1 - 1e-3:
                    continue
            if min_length is not None and i["length"] < min_length:
                continue
            out.append(R.edge_ref(self.body_id, e))
        return out

    @property
    def volume(self) -> float:
        return K.mass_properties(self.shape)["volume_mm3"]

    @property
    def bbox(self):
        return K.bbox(self.shape)


class SketchBuilder:
    def __init__(self, design: "Design", feature):
        self.d, self.feature = design, feature
        self.s: Sketch = feature.sketch

    @property
    def id(self) -> str:
        return self.feature.id

    def _dim(self, kind, refs, expr, pos):
        """Add a driving dimension whose value is the given expression."""
        pkind = "angle" if kind == "angle" else "length"
        pname = self.d.doc.params.add(str(expr), pkind, owner=self.feature.id)
        self.s.add_constraint(kind, refs, param=pname, check=False)

    def line(self, a, b, construction=False) -> int:
        return self.s.add_line(a, b, construction=construction)

    def circle(self, cx, cy, r, diameter=None) -> int:
        cid = self.s.add_circle((cx, cy), self.d.mm(r) if not _is_expr(r) else self.d.eval_len(r))
        if _is_expr(r):
            self._dim("radius", [cid], r, None)
        return cid

    def rect(self, x, y, w, h) -> list[int]:
        """Axis-aligned rectangle from corner (x, y); w/h may be expressions."""
        W, H = self.d.eval_len(w), self.d.eval_len(h)
        pts = [(x, y), (x + W, y), (x + W, y + H), (x, y + H)]
        L = [self.s.add_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        E = self.s.entities
        for i in range(4):
            self.s.add_constraint("coincident", [E[L[i]].pts[1], E[L[(i + 1) % 4]].pts[0]], check=False)
        for i, k in enumerate(("horizontal", "vertical", "horizontal", "vertical")):
            self.s.add_constraint(k, [L[i]], check=False)
        if _is_expr(w):
            self._dim("distance", [L[0]], w, None)
        if _is_expr(h):
            self._dim("distance", [L[1]], h, None)
        return L

    def polygon(self, points) -> list[int]:
        pts = [tuple(p) for p in points]
        L = [self.s.add_line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        from .sketch.ops import join_coincident
        join_coincident(self.s, L)
        return L

    def arc(self, center, start, end) -> int:
        return self.s.add_arc(center, start, end)

    def ellipse(self, cx, cy, major, minor, angle=0.0) -> int:
        return self.s.add_ellipse((cx, cy), (cx + major * math.cos(angle), cy + major * math.sin(angle)), minor)

    def text(self, x, y, text, height=5.0, font="sans", bold=False, italic=False, angle=0.0) -> int:
        return self.s.add_text((x, y), text, height, font, bold, italic, angle)

    def point(self, x, y) -> int:
        return self.s.add_point(x, y)

    def import_file(self, path, origin=(0, 0)) -> list[int]:
        from .sketch.ops import import_2d_file
        return import_2d_file(self.s, path, origin)

    def constrain(self, kind, *refs):
        self.s.add_constraint(kind, list(refs))

    def finish(self) -> "SketchBuilder":
        self.s.solve()
        self.d.doc.rebuild()
        return self

    def profiles(self) -> list[dict]:
        """References to every closed region of the sketch (largest first)."""
        self.finish()
        so = self.d.doc.state.sketches[self.feature.id]
        out = []
        for face in so.profiles:
            uv = K.interior_point(face, so.frame)
            out.append({"sketch": self.feature.id, "uv": [round(uv[0], 9), round(uv[1], 9)]})
        return out

    def profile(self, x, y) -> dict:
        """The smallest region containing the sketch point (x, y)."""
        self.finish()
        so = self.d.doc.state.sketches[self.feature.id]
        if K.profile_at(so.profiles, so.frame, (x, y)) is None:
            raise DesignError(f"no closed profile contains ({x}, {y})")
        return {"sketch": self.feature.id, "uv": [x, y]}

    def curves(self) -> dict:
        return {"sketch": self.feature.id, "entities": [e.id for e in self.s.curves(False)]}


class Design:
    """A parametric design backed by the same Document the GUI edits."""

    def __init__(self, doc: Document | None = None):
        self.doc = doc or Document()

    # ---- construction / io
    @staticmethod
    def open(path: str) -> "Design":
        return Design(Document.load(path))

    def save(self, path: str | None = None, compress: bool = False):
        self.doc.save(path or self.doc.path or "design.f3x", compress)

    def export(self, path: str):
        self.doc.export_bodies(path)

    # ---- parameters
    def param(self, name: str, expr: str, kind: str = "length", comment: str = "") -> str:
        """Create or update a user parameter (``d.param('width', '80 mm')``)."""
        if name in self.doc.params.params:
            self.doc.set_param(name, expr)
        else:
            self.doc.params.add(expr, kind, None, name, comment)
        return name

    def value(self, name: str) -> float:
        return self.doc.params.value(name)

    def eval_len(self, v) -> float:
        return self.doc.params.eval_expr(v, "length") if _is_expr(v) else float(v)

    @staticmethod
    def mm(v) -> float:
        return float(v)

    # ---- features
    def _num(self, d: dict) -> dict:
        return {k: (v if _is_expr(v) else f"{v} mm" if k not in ("angle", "taper", "tip_angle") else f"{v} deg",
                    "angle" if k in ("angle", "taper", "tip_angle") else "length") for k, v in d.items()}

    def _add(self, ftype, data, numeric=None, name=None):
        with self.doc.transaction(ftype):
            f = self.doc.add_feature(ftype, data, numeric=self._num(numeric or {}) | {}, name=name)
        if f.error:
            raise DesignError(f"{f.name}: {f.error}")
        return f

    def sketch(self, plane="XY") -> SketchBuilder:
        """Start a sketch on 'XY'/'XZ'/'YZ', a construction plane id, or a face reference."""
        ref = plane if isinstance(plane, (str, dict)) else plane
        with self.doc.transaction("Sketch"):
            f = self.doc.add_feature("sketch", {"plane": ref}, sketch=Sketch())
        f.sketch.param_value = self.doc.param_value
        self.doc.body_props.setdefault(f.id, {})["visible"] = False
        return SketchBuilder(self, f)

    def _profiles(self, p) -> list[dict]:
        return [p] if isinstance(p, dict) else list(p)

    def extrude(self, profiles, distance, operation="auto", direction="one_side", taper=0, name=None):
        profiles = self._profiles(profiles)
        num = {"distance": distance, "taper": taper}
        if direction == "two_sides":
            num["distance2"] = distance
        data = default_data("extrude") | {"profiles": profiles, "direction": direction, "operation": operation}
        f = self._add("extrude", data, {k: v for k, v in num.items()}, name)
        return self.body_of(f)

    def revolve(self, profiles, axis="Z", angle="360 deg", operation="new"):
        data = default_data("revolve") | {"profiles": self._profiles(profiles), "axis": axis, "operation": operation}
        return self.body_of(self._add("revolve", data, {"angle": angle}))

    def fillet(self, edges, radius, radius_end=None, tangent_chain=True):
        data = default_data("fillet") | {"edges": list(edges), "tangent_chain": tangent_chain,
                                         "fillet_type": "variable" if radius_end else "constant"}
        self._add("fillet", data, {"radius": radius, "radius_end": radius_end or radius})

    def chamfer(self, edges, distance):
        self._add("chamfer", default_data("chamfer") | {"edges": list(edges)}, {"distance": distance, "distance2": distance})

    @staticmethod
    def _face_refs(faces):
        """Accept the dicts returned by ``Selection.faces()`` or raw references."""
        faces = [faces] if isinstance(faces, dict) else list(faces)
        return [f["face"] if "face" in f else f for f in faces]

    def shell(self, faces, thickness, side="inside"):
        self._add("shell", default_data("shell") | {"faces": self._face_refs(faces), "side": side},
                  {"thickness": thickness})

    def hole(self, face_or_sketch, at=None, diameter="6 mm", depth="10 mm", thread: str | None = None,
             points: list | None = None):
        """Drill holes at sketch points, or at ``at=(x, y)`` on a face reference."""
        if isinstance(face_or_sketch, SketchBuilder):
            sk, pts = face_or_sketch, points or []
        else:
            sk = self.sketch({"face": face_or_sketch["face"]} if "face" in face_or_sketch else face_or_sketch)
            pts = [sk.point(*at)]
        sk.finish()
        data = default_data("hole") | {"points": [{"sketch": sk.id, "point": p} for p in pts],
                                       "hole_type": "tapped" if thread else "simple"}
        if thread:
            data["thread"] = thread
        self._add("hole", data, {"diameter": diameter, "depth": depth, "cbore_diameter": "10 mm",
                                 "cbore_depth": "3 mm", "tip_angle": "118 deg"})

    def box(self, x, y, w, l, h, plane="XY", operation="new"):
        f = self._add("box", {"plane": plane, "operation": operation},
                      {"x": x, "y": y, "length": w, "width": l, "height": h})
        return self.body_of(f)

    def cylinder(self, x, y, diameter, height, plane="XY", operation="new"):
        f = self._add("cylinder", {"plane": plane, "operation": operation},
                      {"x": x, "y": y, "diameter": diameter, "height": height})
        return self.body_of(f)

    def rib(self, curves, thickness, height, direction="one_side", operation="join"):
        self._add("rib", {"path": curves, "direction": direction, "operation": operation},
                  {"thickness": thickness, "height": height})

    def thread(self, faces, designation="M6x1", length=None):
        self._add("thread", {"faces": self._face_refs(faces), "designation": designation,
                             "full_length": length is None},
                  {"length": length or "10 mm"})

    def drawing(self, path: str, views=("front", "top", "right"), size="A3", hidden=True, dims=None, bom=False):
        """Write an orthographic drawing sheet (.svg or .dxf) of all visible bodies.

        dims: extra dimensions, e.g. ``{"view": "front", "p1": (0, 0, 0), "p2": (25, 0, 0), "kind": "horizontal"}``
        (kind: horizontal | vertical | aligned; optional "offset" in sheet mm and "text").
        bom: add a parts list (components count as one item, mass from each body's material).
        """
        from . import drawing
        from .core.materials import MATERIALS
        bodies = self.doc.visible_bodies()
        items = []
        if bom:
            groups: dict = {}
            for b in bodies:
                comp = self.doc.component_of(b.id)
                key = comp or self.doc.body_name(b.id)
                g = groups.setdefault(key, [0.0, self.doc.body_material(b.id)])
                g[0] += K.mass_properties(b.shape, MATERIALS.get(self.doc.body_material(b.id), 7.85))["mass_g"]
            items = [(k, v[1], v[0]) for k, v in groups.items()]
        return drawing.export_drawing(K.compound([b.shape for b in bodies]), path, self.doc.name, tuple(views), size,
                                      hidden, dims, items or None)

    def flange(self, face, height="15 mm", angle="90 deg", radius="2 mm", k_factor="0.44", flip=False,
               gap_start="0 mm", gap_end="0 mm"):
        """Bend a wall up from a sheet's edge face (reference from ``Selection.faces``)."""
        self._add("flange", default_data("flange") | {"face": self._face_refs(face), "side": "minus" if flip else "plus"},
                  {"height": height, "angle": angle, "radius": radius, "k_factor": k_factor,
                   "gap_start": gap_start, "gap_end": gap_end})

    def hem(self, face, length="8 mm", gap="1 mm", flip=False, **kw):
        """Fold the sheet edge back on itself (180 deg bend); ``gap`` is the opening between the layers."""
        self.flange(face, height=length, angle="180 deg", radius=f"({gap}) / 2", flip=flip, **kw)

    def flat_pattern(self, path: str, body: Selection | None = None):
        """Write the unfolded sheet as DXF (CUT and BEND layers); returns the developed bounding size."""
        from .core import sheetmetal as SM
        body = body or self.bodies[0]
        bends = self.doc.state.sheet
        cuts, bend_lines = SM.flat_pattern(body.shape, bends)
        SM.write_flat_dxf(cuts, bend_lines, path)
        pts = np.vstack(cuts)
        return tuple((pts.max(axis=0) - pts.min(axis=0)).tolist())

    def component(self, name: str, *bodies: Selection):
        """Group bodies into a named component (moves together under joints, exported as an assembly)."""
        self.doc.set_component([b.body_id for b in bodies], name)

    def joint(self, moving, fixed, kind="rigid", offset="0 mm", angle="0 deg", flip=False, limits=None):
        """Mate a face of the moving part to a face of the fixed part.

        kind: rigid | revolute | slider | cylindrical
        """
        return self._add("joint", default_data("joint") | {"faces": self._face_refs([moving, fixed]), "joint_type": kind,
                                                    "flip": flip, "limits": list(limits) if limits else None},
                  {"offset": offset, "angle": angle})

    def animate(self, joint_feature, values, on_frame=None):
        """Drive a joint's motion parameter through ``values`` (degrees, or mm for sliders); calls ``on_frame(value)``
        after each rebuild.  The last value is kept."""
        f = joint_feature if hasattr(joint_feature, "params") else self.doc.feature(joint_feature)
        key = "offset" if f.data.get("joint_type") == "slider" else "angle"
        unit = " mm" if key == "offset" else " deg"
        for v in values:
            self.doc.set_param(f.params[key], f"{v:g}{unit}")
            if on_frame:
                on_frame(v)

    def mirror(self, body: Selection, plane="YZ", combine=True):
        self._add("mirror", {"bodies": [body.body_id], "plane": plane, "combine": combine})

    def pattern_rect(self, body: Selection, count1, spacing1, axis1="X", count2=1, spacing2=0, axis2="Y"):
        self._add("pattern_rect", {"bodies": [body.body_id], "axis1": axis1, "axis2": axis2, "combine": True},
                  {"count1": str(count1), "spacing1": spacing1, "count2": str(count2), "spacing2": spacing2})

    def combine(self, target: Selection, tools: Iterable[Selection], operation="join"):
        self._add("combine", {"target": target.body_id, "tools": [t.body_id for t in tools], "operation": operation})

    # ---- results
    @property
    def bodies(self) -> list[Selection]:
        return [Selection(self, bid) for bid in self.doc.state.bodies]

    def body_of(self, feature) -> Selection:
        """The (first) body a feature created or modified."""
        st = self.doc.state
        for bid in st.bodies:
            if bid.startswith(feature.id):
                return Selection(self, bid)
        return Selection(self, next(reversed(st.bodies))) if st.bodies else None

    def mass_properties(self, density=1.0) -> dict:
        return K.mass_properties(K.compound([b.shape for b in self.doc.visible_bodies()]), density)

    def undo(self):
        self.doc.undo()


def run_script(path: str, design: Design | None = None, extra: dict | None = None) -> Design:
    """Execute a script file with ``design`` and the API names in scope."""
    design = design or Design()
    ns = {"design": design, "Design": Design, "K": K, "np": np, "math": math, "__name__": "__fission_script__"}
    ns.update(extra or {})
    with open(path, "r", encoding="utf-8") as fh:
        code = compile(fh.read(), path, "exec")
    exec(code, ns)  # noqa: S102 - running the user's own script is the point
    return design
