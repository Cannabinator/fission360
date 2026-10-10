"""Feature definitions: UI specs + rebuild executors.

Every feature type is described declaratively (``FEATURE_TYPES``): its inputs,
their kinds and defaults.  The UI builds the command dialog (with live
preview) from this spec, and the document rebuild calls the executor.  To
add a feature you add a spec entry and an ``_exec_<type>`` function.
"""
from __future__ import annotations

import math

import numpy as np

from . import kernel as K
from . import references as R
from . import threads as TH

OPERATIONS = ["new", "join", "cut", "intersect"]
OP_LABELS = {"new": "New Body", "join": "Join", "cut": "Cut", "intersect": "Intersect"}


def F(key, label, kind, default=None, options=None, show=None, optional=False, tip=""):
    return {"key": key, "label": label, "kind": kind, "default": default, "options": options,
            "show": show, "optional": optional, "tip": tip}


def _op_field(default="new"):
    return F("operation", "Operation", "choice", default, OPERATIONS)


FEATURE_TYPES: dict[str, dict] = {
    "sketch": {"label": "Sketch", "icon": "sketch", "fields": []},
    "extrude": {"label": "Extrude", "icon": "extrude", "key": "E", "fields": [
        F("profiles", "Profiles", "profiles", tip="Select sketch profiles or planar faces"),
        F("direction", "Direction", "choice", "one_side", ["one_side", "symmetric", "two_sides"]),
        F("distance", "Distance", "length", "10 mm"),
        F("distance2", "Distance 2", "length", "10 mm", show=lambda d: d.get("direction") == "two_sides"),
        F("taper", "Taper Angle", "angle", "0 deg"),
        _op_field(),
        F("targets", "Objects To Cut/Join", "bodies", optional=True,
          show=lambda d: d.get("operation") in ("join", "cut", "intersect")),
    ]},
    "revolve": {"label": "Revolve", "icon": "revolve", "fields": [
        F("profiles", "Profiles", "profiles"),
        F("axis", "Axis", "axis", "Y"),
        F("direction", "Direction", "choice", "one_side", ["one_side", "symmetric"]),
        F("angle", "Angle", "angle", "360 deg"),
        _op_field(),
        F("targets", "Objects", "bodies", optional=True,
          show=lambda d: d.get("operation") in ("join", "cut", "intersect")),
    ]},
    "sweep": {"label": "Sweep", "icon": "sweep", "fields": [
        F("profiles", "Profile", "profiles"),
        F("path", "Path", "path", tip="Select connected sketch curves"),
        F("orientation", "Orientation", "choice", "perpendicular", ["perpendicular", "parallel"]),
        _op_field(),
    ]},
    "loft": {"label": "Loft", "icon": "loft", "fields": [
        F("profiles", "Profiles (in order)", "profiles"),
        F("ruled", "Ruled", "bool", False),
        _op_field(),
    ]},
    "hole": {"label": "Hole", "icon": "hole", "key": "H", "fields": [
        F("points", "Center Points", "points", tip="Select sketch points"),
        F("hole_type", "Hole Type", "choice", "simple", ["simple", "counterbore", "countersink", "tapped"]),
        F("thread", "Thread", "choice", "M6x1", list(TH.THREADS), show=lambda d: d.get("hole_type") == "tapped"),
        F("diameter", "Diameter", "length", "6 mm", show=lambda d: d.get("hole_type") != "tapped"),
        F("depth", "Depth", "length", "10 mm"),
        F("cbore_diameter", "Counterbore Diameter", "length", "10 mm",
          show=lambda d: d.get("hole_type") in ("counterbore", "countersink")),
        F("cbore_depth", "Counterbore Depth", "length", "3 mm", show=lambda d: d.get("hole_type") == "counterbore"),
        F("tip_angle", "Drill Point Angle", "angle", "118 deg"),
    ]},
    "rib": {"label": "Rib / Web", "icon": "rib", "fields": [
        F("path", "Profile Curves", "path", tip="Select open or closed sketch curves; they are thickened into a wall"),
        F("thickness", "Thickness", "length", "2 mm"),
        F("height", "Height", "length", "10 mm", tip="Extrusion perpendicular to the sketch plane"),
        F("direction", "Direction", "choice", "one_side", ["one_side", "reverse", "symmetric"]),
        F("operation", "Operation", "choice", "join", ["join", "new", "cut"]),
    ]},
    "thread": {"label": "Thread", "icon": "thread", "fields": [
        F("faces", "Cylindrical Faces", "faces", tip="Select hole or shaft faces for a cosmetic thread"),
        F("designation", "Thread", "choice", "M6x1", list(TH.THREADS)),
        F("full_length", "Full Length", "bool", True),
        F("length", "Length", "length", "10 mm", show=lambda d: not d.get("full_length", True)),
    ]},
    "joint": {"label": "Joint", "icon": "joint", "key": "J", "fields": [
        F("faces", "Faces (moving, then fixed)", "faces",
          tip="Pick the face on the part that moves, then the face it mates to. Parts in the same component move together."),
        F("joint_type", "Motion", "choice", "rigid", ["rigid", "revolute", "slider", "cylindrical"]),
        F("flip", "Flip", "bool", False),
        F("offset", "Offset / Travel", "length", "0 mm",
          tip="Gap between planar faces, or travel along the axis for slider and cylindrical joints"),
        F("angle", "Angle", "angle", "0 deg", tip="Rotation about the joint axis (revolute and cylindrical)"),
    ]},
    "fillet": {"label": "Fillet", "icon": "fillet", "key": "F", "fields": [
        F("edges", "Edges/Faces", "edges", tip="Pick edges, or a face to round all its edges"),
        F("fillet_type", "Radius Type", "choice", "constant", ["constant", "variable"]),
        F("radius", "Radius", "length", "2 mm"),
        F("radius_end", "End Radius", "length", "4 mm", show=lambda d: d.get("fillet_type") == "variable",
          tip="Radius at the far end of each selected edge (linear blend)"),
        F("tangent_chain", "Tangent Chain", "bool", True, show=lambda d: d.get("fillet_type") != "variable"),
    ]},
    "chamfer": {"label": "Chamfer", "icon": "chamfer", "fields": [
        F("edges", "Edges/Faces", "edges", tip="Pick edges, or a face to chamfer all its edges"),
        F("chamfer_type", "Chamfer Type", "choice", "equal", ["equal", "two_distances"]),
        F("tangent_chain", "Tangent Chain", "bool", True),
        F("distance", "Distance", "length", "1 mm"),
        F("distance2", "Distance 2", "length", "1 mm", show=lambda d: d.get("chamfer_type") == "two_distances"),
    ]},
    "shell": {"label": "Shell", "icon": "shell", "fields": [
        F("faces", "Faces To Remove", "faces"),
        F("thickness", "Thickness", "length", "1 mm"),
        F("side", "Direction", "choice", "inside", ["inside", "outside"]),
    ]},
    "draft": {"label": "Draft", "icon": "draft", "fields": [
        F("faces", "Faces", "faces"),
        F("plane", "Pull Direction (plane)", "plane", "XY"),
        F("angle", "Angle", "angle", "3 deg"),
    ]},
    "box": {"label": "Box", "icon": "box", "fields": [
        F("plane", "Plane", "plane", "XY"),
        F("x", "Corner X", "length", "0 mm"), F("y", "Corner Y", "length", "0 mm"),
        F("length", "Length", "length", "20 mm"), F("width", "Width", "length", "20 mm"),
        F("height", "Height", "length", "20 mm"), _op_field(),
    ]},
    "cylinder": {"label": "Cylinder", "icon": "cylinder", "fields": [
        F("plane", "Plane", "plane", "XY"),
        F("x", "Center X", "length", "0 mm"), F("y", "Center Y", "length", "0 mm"),
        F("diameter", "Diameter", "length", "20 mm"), F("height", "Height", "length", "20 mm"),
        _op_field(),
    ]},
    "sphere": {"label": "Sphere", "icon": "sphere", "fields": [
        F("plane", "Plane", "plane", "XY"),
        F("x", "Center X", "length", "0 mm"), F("y", "Center Y", "length", "0 mm"),
        F("z", "Center Z", "length", "0 mm"),
        F("diameter", "Diameter", "length", "20 mm"), _op_field(),
    ]},
    "torus": {"label": "Torus", "icon": "torus", "fields": [
        F("plane", "Plane", "plane", "XY"),
        F("x", "Center X", "length", "0 mm"), F("y", "Center Y", "length", "0 mm"),
        F("major", "Inner Diameter", "length", "30 mm"), F("minor", "Torus Diameter", "length", "8 mm"),
        _op_field(),
    ]},
    "coil": {"label": "Coil", "icon": "coil", "fields": [
        F("plane", "Plane", "plane", "XY"),
        F("x", "Center X", "length", "0 mm"), F("y", "Center Y", "length", "0 mm"),
        F("diameter", "Diameter", "length", "20 mm"), F("pitch", "Pitch", "length", "5 mm"),
        F("turns", "Revolutions", "scalar", "4"), F("section", "Section Size", "length", "2 mm"),
        _op_field(),
    ]},
    "pattern_rect": {"label": "Rectangular Pattern", "icon": "pattern_rect", "fields": [
        F("bodies", "Bodies", "bodies"),
        F("axis1", "Direction 1", "axis", "X"),
        F("count1", "Quantity 1", "scalar", "3"),
        F("spacing1", "Spacing 1", "length", "20 mm"),
        F("axis2", "Direction 2", "axis", "Y"),
        F("count2", "Quantity 2", "scalar", "1"),
        F("spacing2", "Spacing 2", "length", "20 mm"),
        F("combine", "Join Instances", "bool", True),
    ]},
    "pattern_circ": {"label": "Circular Pattern", "icon": "pattern_circ", "fields": [
        F("bodies", "Bodies", "bodies"),
        F("axis", "Axis", "axis", "Z"),
        F("count", "Quantity", "scalar", "6"),
        F("angle", "Total Angle", "angle", "360 deg"),
        F("combine", "Join Instances", "bool", True),
    ]},
    "mirror": {"label": "Mirror", "icon": "mirror", "fields": [
        F("bodies", "Bodies", "bodies"),
        F("plane", "Mirror Plane", "plane", "YZ"),
        F("combine", "Join", "bool", True),
    ]},
    "combine": {"label": "Combine", "icon": "combine", "fields": [
        F("target", "Target Body", "body"),
        F("tools", "Tool Bodies", "bodies"),
        F("operation", "Operation", "choice", "join", ["join", "cut", "intersect"]),
        F("keep_tools", "Keep Tools", "bool", False),
    ]},
    "move": {"label": "Move/Copy", "icon": "move", "key": "M", "fields": [
        F("bodies", "Bodies", "bodies"),
        F("dx", "X Distance", "length", "0 mm"), F("dy", "Y Distance", "length", "0 mm"),
        F("dz", "Z Distance", "length", "0 mm"),
        F("axis", "Rotation Axis", "axis", "Z"),
        F("angle", "Angle", "angle", "0 deg"),
        F("copy", "Create Copy", "bool", False),
    ]},
    "scale": {"label": "Scale", "icon": "scale", "fields": [
        F("bodies", "Bodies", "bodies"),
        F("factor", "Scale Factor", "scalar", "1"),
    ]},
    "split_body": {"label": "Split Body", "icon": "split", "fields": [
        F("body", "Body To Split", "body"),
        F("plane", "Splitting Tool (plane)", "plane", "YZ"),
    ]},
    "remove": {"label": "Remove", "icon": "remove", "fields": [
        F("bodies", "Bodies", "bodies"),
    ]},
    "plane_offset": {"label": "Offset Plane", "icon": "plane", "fields": [
        F("plane", "Reference Plane", "plane", "XY"),
        F("distance", "Distance", "length", "10 mm"),
    ]},
    "plane_angle": {"label": "Plane at Angle", "icon": "plane", "fields": [
        F("axis", "Axis", "axis", "X"),
        F("angle", "Angle", "angle", "45 deg"),
    ]},
    "axis_construct": {"label": "Axis", "icon": "axis", "fields": [
        F("axis", "Through edge / cylinder", "axis", "Z"),
    ]},
    "import": {"label": "Import", "icon": "import", "fields": []},
}

DIRECTION_LABELS = {"one_side": "One Side", "symmetric": "Symmetric", "two_sides": "Two Sides",
                    "simple": "Simple", "counterbore": "Counterbore", "countersink": "Countersink",
                    "equal": "Equal Distance", "two_distances": "Two Distances", "inside": "Inside",
                    "outside": "Outside", "perpendicular": "Perpendicular", "parallel": "Parallel",
                    "join": "Join", "cut": "Cut", "intersect": "Intersect", "new": "New Body"}

NUMERIC_KINDS = {"length", "angle", "scalar"}


def numeric_fields(ftype):
    return [f for f in FEATURE_TYPES[ftype]["fields"] if f["kind"] in NUMERIC_KINDS]


def default_data(ftype) -> dict:
    d = {}
    for f in FEATURE_TYPES[ftype]["fields"]:
        if f["kind"] in NUMERIC_KINDS:
            continue
        if f["kind"] in ("profiles", "edges", "faces", "bodies", "points"):
            d[f["key"]] = []
        elif f["kind"] in ("body", "path"):
            d[f["key"]] = None
        else:
            d[f["key"]] = f["default"]
    return d


# ---------------------------------------------------------------------------
# Boolean application (Fusion "operation" semantics)
# ---------------------------------------------------------------------------

def _intersects(a, b) -> bool:
    lo1, hi1 = K.bbox(a)
    lo2, hi2 = K.bbox(b)
    if np.any(hi1 < lo2 - 1e-6) or np.any(hi2 < lo1 - 1e-6):
        return False
    try:
        d, *_ = K.distance(a, b)
        return d < 1e-6
    except K.KernelError:
        return True


def apply_operation(doc, f, state, tool, op: str, targets: list | None = None, suffix: str = ""):
    """Merge ``tool`` into the model according to ``op``."""
    if tool is None or tool.IsNull():
        raise K.KernelError("feature produced no geometry")
    tool_solids = K.solids(tool) or [tool]
    if op == "new":
        for i, s in enumerate(tool_solids):
            state.add_body(f"{f.id}{suffix}:{i}", s)
        return
    cand = [bid for bid in (targets or state.bodies.keys()) if bid in state.bodies]
    if not targets:
        cand = [bid for bid in cand if doc.body_visible(bid)]
    hit = [bid for bid in cand if _intersects(state.bodies[bid].shape, tool)]
    if op == "join":
        if not hit:
            for i, s in enumerate(tool_solids):
                state.add_body(f"{f.id}{suffix}:{i}", s)
            return
        main = hit[0]
        shape = K.fuse(state.bodies[main].shape, [tool] + [state.bodies[b].shape for b in hit[1:]])
        for b in hit[1:]:
            state.remove_body(b)
        _store_result(state, main, shape)
        return
    if not hit:
        f.warning = "No bodies intersect the feature"
        return
    for bid in hit:
        res = K.cut(state.bodies[bid].shape, tool) if op == "cut" else K.common(state.bodies[bid].shape, tool)
        _store_result(state, bid, res)


def _store_result(state, bid, shape):
    """A boolean can split a body into several lumps -> several bodies."""
    parts = K.solids(shape)
    if not parts:
        state.remove_body(bid)
        return
    state.set_shape(bid, parts[0])
    for i, p in enumerate(parts[1:], 1):
        state.add_body(f"{bid}.{i}", p)


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute(doc, f, state):
    fn = globals().get(f"_exec_{f.type}")
    if fn is None:
        raise K.KernelError(f"unknown feature type '{f.type}'")
    fn(doc, f, state)


def _exec_sketch(doc, f, state):
    frame = R.resolve_plane(state, f.data.get("plane", "XY"))
    sk = f.sketch
    sk.param_value = doc.param_value
    sk.solve()
    state.sketches[f.id] = _sketch_out(frame, sk)
    if not sk.last_ok:
        f.warning = "Sketch could not be fully solved"


def _sketch_out(frame, sk):
    from .document import SketchOut
    # Snapshot so later edits of the live sketch don't mutate cached states
    return SketchOut(frame, sk.copy())


def _profiles(state, f):
    refs = f.data.get("profiles") or []
    if not refs:
        raise K.KernelError("select at least one profile")
    out = []
    for ref in refs:
        face, frame = R.resolve_profile(state, ref)
        out.append(face)
    return out


def _profile_normal(state, ref, face):
    if "face" in ref:
        info = K.face_info(face)
        return np.array(info["normal"])
    return state.sketches[ref["sketch"]].frame.normal


def _exec_extrude(doc, f, state):
    faces = _profiles(state, f)
    d1 = doc.val(f, "distance")
    direction = f.data.get("direction", "one_side")
    taper = doc.val(f, "taper", 0.0)
    tools = []
    for ref, face in zip(f.data["profiles"], faces):
        n = _profile_normal(state, ref, face)
        if direction == "one_side":
            spans = [(0.0, d1)]
        elif direction == "symmetric":
            spans = [(-abs(d1) / 2, abs(d1) / 2)]
        else:
            spans = [(0.0, d1), (0.0, -doc.val(f, "distance2"))]
        for a, b in spans:
            if abs(b - a) < 1e-9:
                raise K.KernelError("distance must not be zero")
            base = K.translate(face, n * a) if abs(a) > 0 else face
            if abs(taper) > 1e-9:
                tools.append(K.tapered_prism(base, n * (b - a), taper if b > a else taper))
            else:
                tools.append(K.prism(base, n * (b - a)))
    tool = tools[0] if len(tools) == 1 else _fuse_all(tools)
    op = f.data.get("operation", "new")
    if op == "auto":
        op = auto_operation(doc, state, tool)
        f.resolved_operation = op
    apply_operation(doc, f, state, tool, op, f.data.get("targets"))


def auto_operation(doc, state, tool) -> str:
    """Fusion-style automatic operation: extruding *into* material cuts,
    extruding from a body face *out of* material joins, otherwise new body."""
    touching = False
    tool_vol = K.mass_properties(tool)["volume_mm3"] or 1.0
    for b in state.bodies.values():
        if not doc.body_visible(b.id) or not _intersects(b.shape, tool):
            continue
        touching = True
        try:
            v = K.mass_properties(K.common(b.shape, tool))["volume_mm3"]
        except K.KernelError:
            v = 0.0
        if v > 1e-6 * tool_vol:
            return "cut"
    return "join" if touching else "new"


def _fuse_all(shapes):
    if len(shapes) == 1:
        return shapes[0]
    return K.fuse(shapes[0], shapes[1:])


def _exec_revolve(doc, f, state):
    faces = _profiles(state, f)
    o, d = R.resolve_axis(state, f.data.get("axis", "Y"))
    ang = doc.val(f, "angle")
    if abs(ang) < 1e-9:
        raise K.KernelError("angle must not be zero")
    ang = max(-2 * math.pi, min(2 * math.pi, ang))
    tools = []
    for face in faces:
        if f.data.get("direction") == "symmetric":
            face = K.rotate(face, o, d, -ang / 2)
        tools.append(K.revolve(face, o, d, ang))
    apply_operation(doc, f, state, _fuse_all(tools), f.data.get("operation", "new"), f.data.get("targets"))


def _exec_sweep(doc, f, state):
    faces = _profiles(state, f)
    path = f.data.get("path")
    if not path:
        raise K.KernelError("select a path")
    edges = R.resolve_sketch_curves(state, path)
    wire = K.wire_from_edges(edges)
    tools = [K.sweep(face, wire, f.data.get("orientation", "perpendicular") == "perpendicular") for face in faces]
    apply_operation(doc, f, state, _fuse_all(tools), f.data.get("operation", "new"))


def _exec_loft(doc, f, state):
    faces = _profiles(state, f)
    if len(faces) < 2:
        raise K.KernelError("select at least two profiles")
    tool = K.loft(faces, True, bool(f.data.get("ruled")))
    apply_operation(doc, f, state, tool, f.data.get("operation", "new"))


def _exec_hole(doc, f, state):
    pts = f.data.get("points") or []
    if not pts:
        raise K.KernelError("select hole center points")
    htype = f.data.get("hole_type", "simple")
    depth = doc.val(f, "depth")
    thread = None
    if htype == "tapped":
        thread = TH.info(f.data.get("thread", "M6x1"))
        dia = thread["tap_drill"]  # drilled to the tap-drill size, thread is cosmetic
    else:
        dia = doc.val(f, "diameter")
    tip = math.degrees(doc.val(f, "tip_angle", math.radians(118)))
    tools = []
    for ref in pts:
        sk = state.sketches.get(ref["sketch"])
        if sk is None or ref["point"] not in sk.sketch.entities:
            raise K.KernelError("hole point no longer exists")
        p = sk.frame.to_world(sk.sketch.xy(ref["point"]))
        n = -sk.frame.normal
        if htype == "counterbore":
            tool = K.hole(p, n, dia, depth, doc.val(f, "cbore_diameter"), doc.val(f, "cbore_depth"), tip)
        elif htype == "countersink":
            tool = K.hole(p, n, dia, depth, 0, 0, tip)
            cd = doc.val(f, "cbore_diameter")
            if cd > dia:
                h = (cd - dia) / 2  # 90 degree countersink
                fr = K.Frame(p + sk.frame.normal * 0.01, sk.frame.xdir, n)
                tool = K.fuse(tool, K.cone(fr, 0, 0, cd / 2 + 0.01, dia / 2, h + 0.01))
        else:
            tool = K.hole(p, n, dia, depth, 0, 0, tip)
        tools.append(tool)
        if thread:
            state.annotations.append({"feature": f.id, "text": TH.label(thread["designation"], depth, True),
                                      "point": (p + n * depth / 2).tolist(), "dir": n.tolist(),
                                      "radius": thread["major"] / 2, "length": depth})
    apply_operation(doc, f, state, _fuse_all(tools), "cut")


def _edges(state, refs, chain=False):
    """Resolve edge (or face -> all its edges) references, grouped by body."""
    by_body: dict[str, list] = {}
    for ref in refs:
        if "face" in ref:
            bid, f = R.resolve_face(state, ref["face"])
            es = K.edges(f)
        else:
            bid, e = R.resolve_edge(state, ref)
            es = [e]
        lst = by_body.setdefault(bid, [])
        for e in es:
            if not any(e.IsSame(x) for x in lst):
                lst.append(e)
    if chain:
        for bid in by_body:
            by_body[bid] = K.tangent_chain(state.bodies[bid].shape, by_body[bid])
    return by_body


def _exec_fillet(doc, f, state):
    refs = f.data.get("edges") or []
    if not refs:
        raise K.KernelError("select edges")
    r = doc.val(f, "radius")
    if r <= 0:
        raise K.KernelError("radius must be positive")
    variable = f.data.get("fillet_type") == "variable"
    r2 = doc.val(f, "radius_end") if variable else None
    if variable and r2 <= 0:
        raise K.KernelError("end radius must be positive")
    chain = f.data.get("tangent_chain", True) and not variable
    for bid, es in _edges(state, refs, chain).items():
        state.set_shape(bid, K.fillet(state.bodies[bid].shape, es, r, r2))


def _exec_chamfer(doc, f, state):
    refs = f.data.get("edges") or []
    if not refs:
        raise K.KernelError("select edges")
    d1 = doc.val(f, "distance")
    d2 = doc.val(f, "distance2") if f.data.get("chamfer_type") == "two_distances" else None
    for bid, es in _edges(state, refs, f.data.get("tangent_chain", True)).items():
        state.set_shape(bid, K.chamfer(state.bodies[bid].shape, es, d1, d2))


def _exec_shell(doc, f, state):
    refs = f.data.get("faces") or []
    if not refs:
        raise K.KernelError("select faces to remove")
    by_body: dict[str, list] = {}
    for ref in refs:
        bid, face = R.resolve_face(state, ref)
        by_body.setdefault(bid, []).append(face)
    t = doc.val(f, "thickness")
    for bid, fs in by_body.items():
        state.set_shape(bid, K.shell(state.bodies[bid].shape, fs, t, f.data.get("side", "inside") == "inside"))


def _exec_draft(doc, f, state):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
    refs = f.data.get("faces") or []
    if not refs:
        raise K.KernelError("select faces")
    frame = R.resolve_plane(state, f.data.get("plane", "XY"))
    ang = doc.val(f, "angle")
    by_body: dict[str, list] = {}
    for ref in refs:
        bid, face = R.resolve_face(state, ref)
        by_body.setdefault(bid, []).append(face)
    for bid, fs in by_body.items():
        dr = BRepOffsetAPI_DraftAngle(state.bodies[bid].shape)
        for face in fs:
            dr.Add(face, K.D(frame.normal), ang, frame.pln(), True)
            if not dr.AddDone():
                raise K.KernelError("draft not possible on a selected face")
        dr.Build()
        K._check(dr, "Draft")
        state.set_shape(bid, dr.Shape())


def _prim_frame(state, f):
    return R.resolve_plane(state, f.data.get("plane", "XY"))


def _exec_box(doc, f, state):
    fr = _prim_frame(state, f)
    s = K.box(fr, doc.val(f, "x"), doc.val(f, "y"), doc.val(f, "length"), doc.val(f, "width"), doc.val(f, "height"))
    apply_operation(doc, f, state, s, f.data.get("operation", "new"))


def _exec_cylinder(doc, f, state):
    fr = _prim_frame(state, f)
    s = K.cylinder(fr, doc.val(f, "x"), doc.val(f, "y"), doc.val(f, "diameter") / 2, doc.val(f, "height"))
    apply_operation(doc, f, state, s, f.data.get("operation", "new"))


def _exec_sphere(doc, f, state):
    fr = _prim_frame(state, f)
    c = fr.to_world((doc.val(f, "x"), doc.val(f, "y"))) + fr.normal * doc.val(f, "z")
    s = K.sphere(c, doc.val(f, "diameter") / 2)
    apply_operation(doc, f, state, s, f.data.get("operation", "new"))


def _exec_torus(doc, f, state):
    fr = _prim_frame(state, f)
    minor = doc.val(f, "minor") / 2
    major = doc.val(f, "major") / 2 + minor
    s = K.torus(fr, doc.val(f, "x"), doc.val(f, "y"), major, minor)
    apply_operation(doc, f, state, s, f.data.get("operation", "new"))


def _exec_coil(doc, f, state):
    fr = _prim_frame(state, f)
    s = K.coil(fr, doc.val(f, "x"), doc.val(f, "y"), doc.val(f, "diameter") / 2, doc.val(f, "pitch"),
               doc.val(f, "turns"), doc.val(f, "section") / 2)
    apply_operation(doc, f, state, s, f.data.get("operation", "new"))


def _bodies(state, f, key="bodies"):
    ids = [b for b in (f.data.get(key) or []) if b in state.bodies]
    if not ids:
        raise K.KernelError("select bodies")
    return ids


def _add_instances(doc, f, state, src_ids, transforms, combine):
    for k, bid in enumerate(src_ids):
        base = state.bodies[bid].shape
        copies = [fn(base) for fn in transforms]
        if combine:
            state.set_shape(bid, K.fuse(base, copies) if copies else base)
        else:
            for i, c in enumerate(copies):
                state.add_body(f"{f.id}:{k}.{i}", c)


def _exec_pattern_rect(doc, f, state):
    ids = _bodies(state, f)
    n1 = max(1, int(round(doc.val(f, "count1"))))
    n2 = max(1, int(round(doc.val(f, "count2", 1))))
    _, d1 = R.resolve_axis(state, f.data.get("axis1", "X"))
    _, d2 = R.resolve_axis(state, f.data.get("axis2", "Y"))
    s1, s2 = doc.val(f, "spacing1"), doc.val(f, "spacing2", 0)
    if n1 * n2 > 2500:
        raise K.KernelError("pattern too large (max 2500 instances)")
    tfs = []
    for i in range(n1):
        for j in range(n2):
            if i == 0 and j == 0:
                continue
            v = d1 * s1 * i + d2 * s2 * j
            tfs.append(lambda s, v=v: K.translate(s, v))
    _add_instances(doc, f, state, ids, tfs, f.data.get("combine", True))


def _exec_pattern_circ(doc, f, state):
    ids = _bodies(state, f)
    n = max(1, int(round(doc.val(f, "count"))))
    o, d = R.resolve_axis(state, f.data.get("axis", "Z"))
    total = doc.val(f, "angle")
    if n > 2500:
        raise K.KernelError("pattern too large")
    full = abs(abs(total) - 2 * math.pi) < 1e-9
    step = total / n if full else (total / (n - 1) if n > 1 else 0)
    tfs = [lambda s, a=step * i: K.rotate(s, o, d, a) for i in range(1, n)]
    _add_instances(doc, f, state, ids, tfs, f.data.get("combine", True))


def _exec_mirror(doc, f, state):
    ids = _bodies(state, f)
    fr = R.resolve_plane(state, f.data.get("plane", "YZ"))
    _add_instances(doc, f, state, ids, [lambda s: K.mirror(s, fr.origin, fr.normal)], f.data.get("combine", True))


def _exec_combine(doc, f, state):
    target = f.data.get("target")
    if target not in state.bodies:
        raise K.KernelError("select a target body")
    tools = [b for b in (f.data.get("tools") or []) if b in state.bodies and b != target]
    if not tools:
        raise K.KernelError("select tool bodies")
    op = f.data.get("operation", "join")
    shapes = [state.bodies[b].shape for b in tools]
    base = state.bodies[target].shape
    res = K.fuse(base, shapes) if op == "join" else K.cut(base, shapes) if op == "cut" else \
        _common_all(base, shapes)
    _store_result(state, target, res)
    if not f.data.get("keep_tools"):
        for b in tools:
            state.remove_body(b)


def _common_all(base, shapes):
    for s in shapes:
        base = K.common(base, s)
    return base


def _exec_move(doc, f, state):
    ids = _bodies(state, f)
    v = np.array([doc.val(f, "dx", 0), doc.val(f, "dy", 0), doc.val(f, "dz", 0)])
    ang = doc.val(f, "angle", 0)
    o, d = R.resolve_axis(state, f.data.get("axis", "Z"))
    for k, bid in enumerate(ids):
        s = state.bodies[bid].shape
        if abs(ang) > 1e-12:
            s = K.rotate(s, o, d, ang)
        if np.linalg.norm(v) > 1e-12:
            s = K.translate(s, v)
        if f.data.get("copy"):
            state.add_body(f"{f.id}:{k}", s)
        else:
            state.set_shape(bid, s)


def _exec_scale(doc, f, state):
    ids = _bodies(state, f)
    k = doc.val(f, "factor")
    if k <= 0:
        raise K.KernelError("scale factor must be positive")
    for bid in ids:
        state.set_shape(bid, K.scale(state.bodies[bid].shape, (0, 0, 0), k))


def _exec_split_body(doc, f, state):
    bid = f.data.get("body")
    if bid not in state.bodies:
        raise K.KernelError("select a body")
    fr = R.resolve_plane(state, f.data.get("plane", "YZ"))
    lo, hi = K.bbox(state.bodies[bid].shape)
    size = float(np.linalg.norm(hi - lo)) * 4 + 10
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    tool = BRepBuilderAPI_MakeFace(fr.pln(), -size, size, -size, size).Face()
    parts = K.split(state.bodies[bid].shape, [tool])
    if len(parts) < 2:
        f.warning = "Splitting tool does not intersect the body"
    state.set_shape(bid, parts[0])
    for i, p in enumerate(parts[1:], 1):
        state.add_body(f"{f.id}:{i}", p)


def _exec_remove(doc, f, state):
    for bid in _bodies(state, f):
        state.remove_body(bid)


def _exec_plane_offset(doc, f, state):
    fr = R.resolve_plane(state, f.data.get("plane", "XY"))
    state.planes[f.id] = fr.offset(doc.val(f, "distance"))


def _exec_plane_angle(doc, f, state):
    o, d = R.resolve_axis(state, f.data.get("axis", "X"))
    ang = doc.val(f, "angle")
    # Start from a plane containing the axis, rotate about it
    ref = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
    n0 = np.cross(d, ref)
    n0 /= np.linalg.norm(n0)
    n = n0 * math.cos(ang) + np.cross(d, n0) * math.sin(ang)
    state.planes[f.id] = K.Frame(o, d, n)


def _exec_axis_construct(doc, f, state):
    state.axes[f.id] = R.resolve_axis(state, f.data.get("axis", "Z"))


def _exec_rib(doc, f, state):
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Arc
    path = f.data.get("path")
    if not path:
        raise K.KernelError("select sketch curves for the rib")
    sk = state.sketches.get(path["sketch"])
    if sk is None:
        raise R.ReferenceError_("referenced sketch is missing")
    t, h = doc.val(f, "thickness"), doc.val(f, "height")
    if t <= 0 or abs(h) < 1e-9:
        raise K.KernelError("thickness and height must be positive")
    wire = K.wire_from_edges(R.resolve_sketch_curves(state, path))
    pln = sk.frame.pln()

    def band(d):
        mk = BRepOffsetAPI_MakeOffset(wire, GeomAbs_Arc, False)
        mk.Perform(float(d))
        if not mk.IsDone():
            raise K.KernelError("could not thicken the curves (distance too large for this shape)")
        w = K.subshapes(mk.Shape(), K.TopAbs_WIRE)[0]
        return BRepBuilderAPI_MakeFace(pln, w, True).Face()

    if BRep_Tool.IsClosed_s(wire):
        outer, inner = band(t / 2), band(-t / 2)
        tool = K.cut(K.prism(outer, sk.frame.normal * h), K.prism(inner, sk.frame.normal * h))
    else:
        try:
            tool = K.prism(band(t / 2), sk.frame.normal * h)
        except K.KernelError:
            tool = _straight_ribs(R.resolve_sketch_curves(state, path), sk.frame, t, h)
    d = f.data.get("direction", "one_side")
    if d == "reverse":
        tool = K.translate(tool, -sk.frame.normal * h)
    elif d == "symmetric":
        tool = K.translate(tool, -sk.frame.normal * h / 2)
    apply_operation(doc, f, state, tool, f.data.get("operation", "join"))


def _straight_ribs(edges, frame, t, h):
    """Thin walls for straight sketch segments (OCCT cannot offset a lone line):
    one slab per segment, with round joints so corners stay filled."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    tools = []
    n = frame.normal
    for e in edges:
        info = K.edge_info(e)
        if info["type"] != "line":
            raise K.KernelError("could not thicken the curves - use straight segments or a closed shape")
        a, b = np.array(info["start"]), np.array(info["end"])
        side = np.cross(n, (b - a) / np.linalg.norm(b - a)) * t / 2
        poly = BRepBuilderAPI_MakePolygon()
        for q in (a + side, b + side, b - side, a - side):
            poly.Add(K.P(q))
        poly.Close()
        tools.append(K.prism(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face(), n * h))
        if len(edges) > 1:
            for q in (a, b):
                tools.append(K.cylinder(K.Frame(q, frame.xdir, n), 0, 0, t / 2, h))
    return _fuse_all(tools)


def _exec_thread(doc, f, state):
    refs = f.data.get("faces") or []
    if not refs:
        raise K.KernelError("select cylindrical faces")
    th = TH.info(f.data.get("designation", "M6x1"))
    for ref in refs:
        bid, face = R.resolve_face(state, ref)
        fi = K.face_info(face)
        if fi["type"] != "cylinder":
            raise K.KernelError("threads can only be applied to cylindrical faces")
        axis = np.array(fi["axis_dir"])
        origin = np.array(fi["axis_origin"])
        pt = np.array(fi["point"])
        internal = float(np.dot(np.array(fi["normal"]), origin + axis * np.dot(pt - origin, axis) - pt)) > 0
        dia = 2 * fi["radius"]
        expect = th["tap_drill"] if internal else th["major"]
        if abs(dia - expect) > 0.12 * expect:
            f.warning = (f"Face diameter {dia:.3g} mm does not match {th['designation']} "
                         f"({'tap drill' if internal else 'major diameter'} {expect:.3g} mm)")
        lo, hi = K.bbox(face)
        flen = float(abs(np.dot(hi - lo, np.abs(axis))))
        length = flen if f.data.get("full_length", True) else min(doc.val(f, "length"), flen)
        state.annotations.append({"feature": f.id, "text": TH.label(th["designation"], length, internal),
                                  "point": fi["center"], "dir": axis.tolist(), "radius": th["major"] / 2,
                                  "length": length})


def _joint_frame(face):
    """Joint origin and direction of a face: plane -> (centre, outward normal); cylinder -> (centre on axis, axis)."""
    fi = K.face_info(face)
    if fi["type"] == "plane":
        return np.array(fi["center"]), np.array(fi["normal"]), "plane"
    if fi["type"] in ("cylinder", "cone"):
        axis, org = np.array(fi["axis_dir"]), np.array(fi["axis_origin"])
        c = np.array(fi["center"])
        return org + axis * float(np.dot(c - org, axis)), axis, "cylinder"
    raise K.KernelError("joints need planar or cylindrical faces")


def _exec_joint(doc, f, state):
    refs = f.data.get("faces") or []
    if len(refs) < 2:
        raise K.KernelError("select the moving face, then the face it mates to")
    mid, mface = R.resolve_face(state, refs[0])
    fid, fface = R.resolve_face(state, refs[1])
    if mid == fid:
        raise K.KernelError("the two faces belong to the same body")
    mo, md, mk = _joint_frame(mface)
    fo, fd, fk = _joint_frame(fface)
    jt = f.data.get("joint_type", "rigid")
    # planes mate face-to-face (normals oppose); axes align along the fixed direction
    target = -fd if (mk == "plane" and fk == "plane") else fd
    if f.data.get("flip"):
        target = -target
    axis, ang = K.rotation_between(md, target)
    off, rot = doc.val(f, "offset", 0.0), doc.val(f, "angle", 0.0)
    lim = f.data.get("limits")            # [min, max] on the joint's motion: degrees, or mm for sliders
    if lim and jt != "rigid":
        if jt == "slider":
            clamped = min(max(off, lim[0]), lim[1])
            if clamped != off:
                f.warning = f"Travel limited to {lim[0]:g}..{lim[1]:g} mm"
            off = clamped
        else:
            lo, hi = math.radians(lim[0]), math.radians(lim[1])
            clamped = min(max(rot, lo), hi)
            if abs(clamped - rot) > 1e-12:
                f.warning = f"Rotation limited to {lim[0]:g}..{lim[1]:g} deg"
            rot = clamped
    gap_dir = fd if fk == "plane" else target       # offset pushes the part away from a mating plane
    if jt in ("rigid", "revolute"):
        shift = gap_dir * off if fk == "plane" else np.zeros(3)
    elif jt == "slider":
        shift = (fd if fk == "plane" else target) * off
    else:
        shift = fd * off
    comp = doc.component_of(mid)
    movers = [b for b in state.bodies if b == mid or (comp and doc.component_of(b) == comp)]
    if fid in movers:
        raise K.KernelError("the fixed face is on a part that moves with the first one")
    for bid in movers:
        s = state.bodies[bid].shape
        if ang > 1e-12:
            s = K.rotate(s, mo, axis, ang)
        # after the rotation the moving origin is unchanged; bring it onto the fixed origin
        s = K.translate(s, fo - mo)
        if jt in ("revolute", "cylindrical") and abs(rot) > 1e-12:
            s = K.rotate(s, fo, target, rot)
        if np.linalg.norm(shift) > 1e-12:
            s = K.translate(s, shift)
        state.set_shape(bid, s)


def _exec_import(doc, f, state):
    import base64
    import zlib
    for i, blob in enumerate(f.data.get("shapes", [])):
        shape = K.shape_from_bytes(zlib.decompress(base64.b64decode(blob)))
        state.add_body(f"{f.id}:{i}", shape)


def encode_shape(shape) -> str:
    import base64
    import zlib
    return base64.b64encode(zlib.compress(K.shape_to_bytes(shape), 6)).decode()
