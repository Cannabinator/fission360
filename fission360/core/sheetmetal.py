"""Sheet metal: bent flanges and flat patterns.

A sheet body is an ordinary thin solid (e.g. an extruded plate).  A *flange*
attaches a bent wall to one of its edge faces: the face is revolved about the
bend axis (inside radius R, so the neutral line sits at ``R + K*t``) and then
extruded straight for the flange height.  Every flange records its bend in
``ModelState.sheet`` so the flat pattern is derived analytically: the base
face outline plus, per flange, a rectangle of developed length

    BA + height,   BA = angle * (R + K * t)      (bend allowance)

attached along the bend line.
"""
from __future__ import annotations

import math

import numpy as np

from . import kernel as K


def edge_face_frame(face):
    """For a rectangular sheet edge face: (outward normal o, thickness dir w, edge dir u, t, length, w_lo, w_hi, centre)."""
    fi = K.face_info(face)
    if fi["type"] != "plane":
        raise K.KernelError("a flange needs a planar sheet edge face")
    o = np.array(fi["normal"], float)
    o /= np.linalg.norm(o)
    pts = np.array([K.vertex_point(v) for v in K.vertices(face)], float)
    c = np.array(fi["center"], float)
    best = None            # the longest straight edge gives the rectangle's own axes
    for e in K.edges(face):
        ei = K.edge_info(e)
        if ei["type"] == "line" and (best is None or ei["length"] > best[0]):
            best = (ei["length"], np.array(ei["tangent"], float))
    if best is None:
        raise K.KernelError("sheet edge face must be a rectangle")
    u0 = best[1] / np.linalg.norm(best[1])
    w0 = np.cross(o, u0)
    sp_u = pts @ u0
    sp_w = pts @ w0
    length, t = float(sp_u.max() - sp_u.min()), float(sp_w.max() - sp_w.min())
    if t > length:                       # thickness is the short side
        u0, w0 = w0, -u0
        length, t = t, length
    if w0[int(np.argmax(np.abs(w0)))] < 0:        # "plus" = towards positive world axes, so it is predictable
        w0, u0 = -w0, -u0
    return o, w0, u0, t, length, c


def make_flange(face, height, angle, radius, k_factor=0.44, toward_plus=True, previous=()):
    """Bent flange solid + bend record for the given sheet edge face."""
    o, w, u, t, length, c = edge_face_frame(face)
    if not toward_plus:
        w = -w
    pts = np.array([K.vertex_point(v) for v in K.vertices(face)], float)
    w_hi = float((pts @ w).max())
    wc = float(c @ w)
    axis_origin = c + w * ((w_hi - wc) + radius)           # centre of the inside bend radius
    axis = np.cross(o, w)                                    # rotating o toward w
    axis /= np.linalg.norm(axis)
    parts = []
    if angle > 1e-9:
        parts.append(K.revolve(face, axis_origin, axis, angle))
    end_face = K.rotate(face, axis_origin, axis, angle)
    tdir = o * math.cos(angle) + w * math.sin(angle)
    if height > 1e-9:
        parts.append(K.prism(end_face, tdir * height))
    solid = parts[0] if len(parts) == 1 else K.fuse(parts[0], parts[1:])
    r = c - axis_origin                                    # Rodrigues rotation of the face centre
    rc = axis_origin + r * math.cos(angle) + np.cross(axis, r) * math.sin(angle) + axis * float(axis @ r) * (1 - math.cos(angle))
    tip = {"center": (rc + tdir * height).tolist()}
    parent = None
    for i, pb in enumerate(previous):                    # attached to the tip face of an earlier flange?
        if np.linalg.norm(c - np.array(pb["end_center"])) < max(0.05 * t, 0.01) and \
                float(np.dot(o, pb["end_normal"])) > 0.999:
            parent = i
    rec = {"parent": parent, "end_center": tip["center"], "end_normal": [float(x) for x in tdir],
           "origin": c.tolist(), "outward": o.tolist(), "edge": u.tolist(), "length": length, "thickness": t,
           "angle": angle, "radius": radius, "height": height, "k": k_factor}
    return solid, rec


def bend_allowance(angle, radius, thickness, k):
    return angle * (radius + k * thickness)


def flat_pattern(shape, bends: list):
    """Return (cut polylines, bend polylines) in 2-D sheet coordinates (mm) for a body with flanges.

    Bends attached to the base sheet unfold outward from the base outline; a bend attached to the tip of
    another flange continues from that flange's far edge (chains of any length)."""
    if not bends:
        raise K.KernelError("no bends recorded - this is already flat")
    roots = [b for b in bends if b.get("parent") is None]
    if not roots:
        raise K.KernelError("no bend is attached to the base sheet")
    w = np.cross(np.array(roots[0]["outward"]), np.array(roots[0]["edge"]))
    w /= np.linalg.norm(w)
    best = None
    for f in K.faces(shape):
        fi = K.face_info(f)
        if fi["type"] == "plane" and abs(abs(float(np.dot(fi["normal"], w))) - 1) < 1e-6:
            if best is None or fi["area"] > best[0]:
                best = (fi["area"], f, fi)
    if best is None:
        raise K.KernelError("could not find the sheet's base face")
    _, base, bi = best
    n = np.array(bi["normal"], float)
    ex = np.array(roots[0]["edge"], float)
    ex -= n * float(ex @ n)
    ex /= np.linalg.norm(ex)
    ey = np.cross(n, ex)
    org = np.array(bi["center"], float)

    def to2(p):
        d = np.asarray(p, float) - org
        return np.array([float(d @ ex), float(d @ ey)])

    def dir2(v):
        d = to2(org + np.asarray(v, float)) - to2(org)
        return d / np.linalg.norm(d)

    placed = []                                   # per bend: dict(a, z, out, dev, far_a, far_z)
    for i, b in enumerate(bends):
        u, c = np.array(b["edge"], float), np.array(b["origin"], float)
        dev = bend_allowance(b["angle"], b["radius"], b["thickness"], b["k"]) + b["height"]
        par = b.get("parent")
        if par is None:
            a, z = to2(c - u * b["length"] / 2), to2(c + u * b["length"] / 2)
            out = dir2(b["outward"])
        else:
            pp, pb = placed[par], bends[par]
            e2 = dir2(u)
            off = float((c - np.array(pb["end_center"], float)) @ np.array(pb["edge"], float))
            pu = dir2(pb["edge"])
            mid = (pp["far_a"] + pp["far_z"]) / 2 + pu * off
            a, z = mid - e2 * b["length"] / 2, mid + e2 * b["length"] / 2
            out = pp["out"]
        placed.append({"a": a, "z": z, "out": out, "dev": dev, "far_a": a + out * dev, "far_z": z + out * dev})

    cuts, bend_lines = [], []
    base_segs = [(p["a"], p["z"]) for p, b in zip(placed, bends) if b.get("parent") is None]
    for e in K.edges(base):
        pl = np.array([to2(p) for p in K.edge_polyline(e, 0.05)])
        if len(pl) >= 2 and not any(_same_seg(pl[0], pl[-1], a, z) for a, z in base_segs):
            cuts.append(pl)
    for i, (p, b) in enumerate(zip(placed, bends)):
        bend_lines.append(np.array([p["a"], p["z"]]))
        cuts += [np.array([p["a"], p["far_a"]]), np.array([p["z"], p["far_z"]])]
        has_child = any(c.get("parent") == i and abs(c["length"] - b["length"]) < 0.05 for c in bends)
        if not has_child:
            cuts.append(np.array([p["far_a"], p["far_z"]]))
    return cuts, bend_lines


def _same_seg(p0, p1, a, z, tol=0.05):
    return (np.linalg.norm(p0 - a) < tol and np.linalg.norm(p1 - z) < tol) or \
           (np.linalg.norm(p0 - z) < tol and np.linalg.norm(p1 - a) < tol)


def write_flat_dxf(cuts, bend_lines, path: str):
    o = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "TABLES",
         "0", "TABLE", "2", "LTYPE", "70", "2",
         "0", "LTYPE", "2", "CONTINUOUS", "70", "0", "3", "Solid", "72", "65", "73", "0", "40", "0.0",
         "0", "LTYPE", "2", "DASHED", "70", "0", "3", "Dashed", "72", "65", "73", "2", "40", "4.5", "49", "3.0", "49", "-1.5",
         "0", "ENDTAB", "0", "TABLE", "2", "LAYER", "70", "2",
         "0", "LAYER", "2", "CUT", "70", "0", "62", "7", "6", "CONTINUOUS",
         "0", "LAYER", "2", "BEND", "70", "0", "62", "5", "6", "DASHED",
         "0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def pl(points, layer):
        o.extend(["0", "POLYLINE", "8", layer, "66", "1", "70", "0"])
        for x, y in points:
            o.extend(["0", "VERTEX", "8", layer, "10", f"{x:.5f}", "20", f"{y:.5f}", "30", "0.0"])
        o.extend(["0", "SEQEND", "8", layer])

    for p in cuts:
        pl(p, "CUT")
    for p in bend_lines:
        pl(p, "BEND")
    o.extend(["0", "ENDSEC", "0", "EOF"])
    with open(path, "w", encoding="latin-1") as fh:
        fh.write("\n".join(o) + "\n")
