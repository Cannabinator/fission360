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


def make_flange(face, height, angle, radius, k_factor=0.44, toward_plus=True):
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
    rec = {"origin": c.tolist(), "outward": o.tolist(), "edge": u.tolist(), "length": length, "thickness": t,
           "angle": angle, "radius": radius, "height": height, "k": k_factor}
    return solid, rec


def bend_allowance(angle, radius, thickness, k):
    return angle * (radius + k * thickness)


def flat_pattern(shape, bends: list):
    """Return (cut polylines, bend polylines) in 2-D sheet coordinates (mm) for a body with flanges."""
    # base face: largest planar face whose normal is the sheet thickness direction
    if not bends:
        raise K.KernelError("no bends recorded - this is already flat")
    t = bends[0]["thickness"]
    # the sheet normal is perpendicular to every bend's outward normal and edge direction
    w = np.cross(np.array(bends[0]["outward"]), np.array(bends[0]["edge"]))
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
    ex = np.array(bends[0]["edge"], float)
    ex -= n * float(ex @ n)
    ex /= np.linalg.norm(ex)
    ey = np.cross(n, ex)
    org = np.array(bi["center"], float)

    def to2(p):
        d = np.asarray(p, float) - org
        return np.array([float(d @ ex), float(d @ ey)])

    cuts, bend_lines = [], []
    bend_segs = []
    for b in bends:
        o = np.array(b["outward"], float)
        u = np.array(b["edge"], float)
        c = np.array(b["origin"], float)
        a = to2(c - u * b["length"] / 2)
        z = to2(c + u * b["length"] / 2)
        out2 = to2(c + o) - to2(c)
        out2 /= np.linalg.norm(out2)
        dev = bend_allowance(b["angle"], b["radius"], b["thickness"], b["k"]) + b["height"]
        bend_segs.append((a, z, out2, dev))
        bend_lines.append(np.array([a, z]))
    for e in K.edges(base):
        pl = np.array([to2(p) for p in K.edge_polyline(e, 0.05)])
        if len(pl) < 2:
            continue
        shared = any(_same_seg(pl[0], pl[-1], a, z) for a, z, _, _ in bend_segs)
        if not shared:
            cuts.append(pl)
    for a, z, out2, dev in bend_segs:
        a2, z2 = a + out2 * dev, z + out2 * dev
        cuts += [np.array([a, a2]), np.array([a2, z2]), np.array([z2, z])]
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
