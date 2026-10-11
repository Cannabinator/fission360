"""Persistent references to geometry (the "topological naming" problem).

Features such as Fillet or Sketch-on-face refer to faces/edges of bodies
produced by earlier features.  Shape indices are not stable across rebuilds,
so we store a *geometric signature* (type, centre, normal/tangent, size) and
re-resolve it against the current geometry by best match, scaled by body
size so that parametric edits (a longer extrude, a larger radius) still
resolve to the "same" face or edge.  Sketch profiles are referenced by an
interior point, which is how Fusion itself keeps profile selections stable.
"""
from __future__ import annotations

import numpy as np

from . import kernel as K


class ReferenceError_(Exception):
    pass


def face_ref(body_id: str, face) -> dict:
    info = K.face_info(face)
    sig = {k: info[k] for k in ("type", "center", "normal", "area") if k in info}
    return {"body": body_id, "sig": sig}


def edge_ref(body_id: str, edge) -> dict:
    info = K.edge_info(edge)
    sig = {k: info[k] for k in ("type", "mid", "tangent", "length") if k in info}
    return {"body": body_id, "sig": sig}


def _scale(shape) -> float:
    lo, hi = K.bbox(shape)
    return float(np.linalg.norm(hi - lo)) or 1.0


def _face_score(sig, info, scale):
    if sig["type"] != info["type"]:
        return 1e9
    d = np.linalg.norm(np.subtract(sig["center"], info["center"])) / scale
    n = 1.0 - float(np.dot(sig["normal"], info["normal"]))
    a = abs(sig["area"] - info["area"]) / max(sig["area"], info["area"], 1e-9)
    return d * 2.0 + n * 2.0 + a * 0.5


def _edge_score(sig, info, scale):
    if sig["type"] != info["type"]:
        return 1e9
    d = np.linalg.norm(np.subtract(sig["mid"], info["mid"])) / scale
    t = 1.0 - abs(float(np.dot(sig["tangent"], info["tangent"])))
    ln = abs(sig["length"] - info["length"]) / max(sig["length"], info["length"], 1e-9)
    return d * 2.0 + t * 2.0 + ln * 0.5


MAX_SCORE = 1.2


def _candidates(state, body_id):
    if body_id in state.bodies:
        return [(body_id, state.bodies[body_id].shape)]
    return [(bid, b.shape) for bid, b in state.bodies.items()]


def resolve_face(state, ref) -> tuple[str, object]:
    best = (1e9, None, None)
    for bid, shape in _candidates(state, ref.get("body")):
        sc = _scale(shape)
        for f in K.faces(shape):
            s = _face_score(ref["sig"], K.face_info(f), sc)
            if s < best[0]:
                best = (s, bid, f)
    if best[2] is None or best[0] > MAX_SCORE:
        raise ReferenceError_("referenced face no longer exists")
    return best[1], best[2]


def resolve_edge(state, ref) -> tuple[str, object]:
    best = (1e9, None, None)
    for bid, shape in _candidates(state, ref.get("body")):
        sc = _scale(shape)
        for e in K.edges(shape):
            s = _edge_score(ref["sig"], K.edge_info(e), sc)
            if s < best[0]:
                best = (s, bid, e)
    if best[2] is None or best[0] > MAX_SCORE:
        raise ReferenceError_("referenced edge no longer exists")
    return best[1], best[2]


# ---------------------------------------------------------------------------
# Planes, axes, profiles
# ---------------------------------------------------------------------------

def resolve_plane(state, ref) -> K.Frame:
    if isinstance(ref, str):
        if ref in K.ORIGIN_FRAMES:
            return K.ORIGIN_FRAMES[ref]
        raise ReferenceError_(f"unknown plane '{ref}'")
    if "plane" in ref:
        fr = state.planes.get(ref["plane"])
        if fr is None:
            raise ReferenceError_("referenced construction plane is missing")
        return fr
    if "face" in ref:
        _, f = resolve_face(state, ref["face"])
        info = K.face_info(f)
        if info["type"] != "plane":
            raise ReferenceError_("face is not planar")
        x = np.array(info["xdir"])
        n = np.array(info["normal"])
        # Use a stable sketch x-axis: prefer world X / Y projected on the plane
        for cand in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])):
            if abs(np.dot(cand, n)) < 0.99:
                x = cand
                break
        # Origin: projection of the world origin onto the plane keeps sketch
        # coordinates aligned with the model coordinate system
        c = np.array(info["center"])
        o = np.dot(c, n) * n
        return K.Frame(o, x, n)
    if "sketch" in ref:
        sk = state.sketches.get(ref["sketch"])
        if sk is None:
            raise ReferenceError_("referenced sketch is missing")
        return sk.frame
    raise ReferenceError_("invalid plane reference")


def resolve_axis(state, ref) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(ref, str):
        if ref in K.ORIGIN_AXES:
            o, d = K.ORIGIN_AXES[ref]
            return np.array(o, float), np.array(d, float)
        raise ReferenceError_(f"unknown axis '{ref}'")
    if "sketch" in ref:
        sk = state.sketches.get(ref["sketch"])
        if sk is None:
            raise ReferenceError_("referenced sketch is missing")
        e = sk.sketch.entities.get(ref["entity"])
        if e is None or e.kind != "line":
            raise ReferenceError_("axis must be a sketch line")
        a, b = (sk.frame.to_world(sk.sketch.xy(p)) for p in e.pts)
        d = b - a
        return a, d / np.linalg.norm(d)
    if "edge" in ref:
        _, e = resolve_edge(state, ref["edge"])
        info = K.edge_info(e)
        if info["type"] == "line":
            return np.array(info["start"]), np.array(info["tangent"])
        if info["type"] == "circle":
            return np.array(info["center"]), np.array(info["axis"])
        raise ReferenceError_("edge cannot be used as an axis")
    if "face" in ref:
        _, f = resolve_face(state, ref["face"])
        info = K.face_info(f)
        if "axis_dir" in info:
            return np.array(info["axis_origin"]), np.array(info["axis_dir"])
        raise ReferenceError_("face has no axis")
    if "axis" in ref:
        ax = state.axes.get(ref["axis"])
        if ax is None:
            raise ReferenceError_("construction axis is missing")
        return ax
    raise ReferenceError_("invalid axis reference")


def resolve_profile(state, ref):
    """Return a planar face for a profile reference (sketch region or face)."""
    if "face" in ref:
        _, f = resolve_face(state, ref["face"])
        return f, None
    sk = state.sketches.get(ref["sketch"])
    if sk is None:
        raise ReferenceError_("referenced sketch is missing")
    f = K.profile_at(sk.profiles, sk.frame, ref["uv"])
    if f is None:
        raise ReferenceError_("profile no longer exists")
    return f, sk.frame


def resolve_sketch_curves(state, ref) -> list:
    sk = state.sketches.get(ref["sketch"])
    if sk is None:
        raise ReferenceError_("referenced sketch is missing")
    out = []
    for eid in ref["entities"]:
        e = sk.sketch.entities.get(eid)
        if e is None:
            raise ReferenceError_("path curve no longer exists")
        edge = K.curve_edge(sk.sketch, e, sk.frame)
        if edge is not None:
            out.append(edge)
    return out


def describe(ref) -> str:
    if isinstance(ref, str):
        return ref
    if "sketch" in ref and "uv" in ref:
        return "Profile"
    if "face" in ref:
        return "Face"
    if "edge" in ref:
        return "Edge"
    if "plane" in ref:
        return "Plane"
    if "sketch" in ref and "entity" in ref:
        return "Sketch line"
    if "sketch" in ref and "entities" in ref:
        return f"Path ({len(ref['entities'])})"
    if "sketch" in ref:
        return "Sketch"
    if "body" in ref and "sig" in ref:
        return "Face" if "normal" in ref["sig"] else "Edge"
    return "?"
