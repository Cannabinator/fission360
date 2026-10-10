"""Sketch editing operations that work on a :class:`Sketch` without any UI:
copy/mirror/pattern, offset, extend, and 2D exchange (DXF / SVG).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import numpy as np

from . import geometry2d as g2
from .model import Sketch, SketchError

TOL = 1e-6


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def join_coincident(sk: Sketch, new_ids, tol: float = TOL) -> int:
    """Add coincident constraints between endpoints of ``new_ids`` curves that
    lie on top of each other (used after copy/offset/import so loops stay closed)."""
    pts = []
    for cid in new_ids:
        e = sk.entities.get(cid)
        if e is None:
            continue
        if e.kind in ("line", "spline"):
            pts += [e.pts[0], e.pts[-1]]
        elif e.kind == "arc":
            pts += [e.pts[1], e.pts[2]]
    n = 0
    used = set()
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if a == b or (a, b) in used:
                continue
            if sk.entities[a].owner == sk.entities[b].owner:
                continue
            if math.dist(sk.xy(a), sk.xy(b)) < tol:
                sk.add_constraint("coincident", [a, b], check=False)
                used.add((a, b))
                n += 1
    return n


def transform_curves(sk: Sketch, ids, fn, mirror: bool = False) -> list[int]:
    """Copy curves through the point map ``fn`` (uv -> uv).  ``mirror`` flips
    arc direction so arcs stay counter-clockwise."""
    out = []
    for cid in ids:
        e = sk.entities[cid]
        P = [tuple(fn(np.array(sk.xy(p)))) for p in e.pts]
        if e.kind == "line":
            out.append(sk.add_line(P[0], P[1], construction=e.construction))
        elif e.kind == "circle":
            out.append(sk.add_circle(P[0], e.r, construction=e.construction))
        elif e.kind == "arc":
            c, s_, t_ = P
            out.append(sk.add_arc(c, t_, s_, construction=e.construction) if mirror
                       else sk.add_arc(c, s_, t_, construction=e.construction))
        elif e.kind == "spline":
            out.append(sk.add_spline(P, construction=e.construction))
        elif e.kind == "ellipse":
            out.append(sk.add_ellipse(P[0], P[1], e.r, construction=e.construction))
        elif e.kind == "text":
            a0 = np.array(sk.xy(e.pts[0]))
            d = fn(a0 + np.array([math.cos(e.angle), math.sin(e.angle)])) - fn(a0)
            ang = math.atan2(d[1], d[0])
            out.append(sk.add_text(P[0], e.text, e.height, e.font, e.bold, e.italic, ang, e.construction))
    join_coincident(sk, out)
    return out


def mirror_curves(sk: Sketch, ids, axis_line_id: int) -> list[int]:
    ln = sk.entities[axis_line_id]
    a, b = np.array(sk.xy(ln.pts[0])), np.array(sk.xy(ln.pts[1]))
    d = b - a
    n = np.linalg.norm(d)
    if n < TOL:
        raise SketchError("mirror line has zero length")
    u = d / n

    def fn(p):
        v = p - a
        return a + 2 * np.dot(v, u) * u - v

    out = transform_curves(sk, ids, fn, mirror=True)
    # keep the copy symmetric when the original is edited (points / circle centres)
    for src, dst in zip(ids, out):
        se, de = sk.entities[src], sk.entities[dst]
        if se.kind in ("line", "circle", "spline", "arc"):
            sp = [se.pts[0], se.pts[1]] if se.kind == "line" else [se.pts[0]]
            dp = [de.pts[0], de.pts[1]] if se.kind == "line" else [de.pts[0]]
            for p, q in zip(sp, dp):
                try:
                    sk.add_constraint("symmetric", [p, q, axis_line_id], check=False)
                except SketchError:
                    pass
        if se.kind in ("circle", "arc"):
            sk.add_constraint("equal", [src, dst], check=False)
    return out


def pattern_rect(sk: Sketch, ids, nx: int, dx: float, ny: int = 1, dy: float = 0.0) -> list[int]:
    out = []
    for i in range(nx):
        for j in range(ny):
            if i == 0 and j == 0:
                continue
            off = np.array([dx * i, dy * j])
            out += transform_curves(sk, ids, lambda p, off=off: p + off)
    return out


def pattern_circ(sk: Sketch, ids, center, count: int, total_angle: float = 2 * math.pi) -> list[int]:
    c = np.asarray(center, float)
    full = abs(abs(total_angle) - 2 * math.pi) < 1e-9
    step = total_angle / count if full else (total_angle / (count - 1) if count > 1 else 0.0)
    out = []
    for k in range(1, count):
        ca, sa = math.cos(step * k), math.sin(step * k)
        R = np.array([[ca, -sa], [sa, ca]])
        out += transform_curves(sk, ids, lambda p, R=R: c + R @ (p - c))
    return out


def extend_line(sk: Sketch, line_id: int, end_pid: int) -> bool:
    """Extend a line's end to the nearest curve ahead of it."""
    ln = sk.entities[line_id]
    if end_pid not in ln.pts:
        return False
    other = ln.pts[0] if end_pid == ln.pts[1] else ln.pts[1]
    a, b = np.array(sk.xy(other)), np.array(sk.xy(end_pid))
    d = b - a
    L = np.linalg.norm(d)
    if L < TOL:
        return False
    u = d / L
    best = None
    for o in sk.curves():
        if o.id == line_id:
            continue
        if o.kind == "line":
            c, e2 = np.array(sk.xy(o.pts[0])), np.array(sk.xy(o.pts[1]))
            r = g2.line_line(a, a + u, c, e2)
            if r and r[1] > L + 1e-6 and -1e-9 <= r[2] <= 1 + 1e-9:
                cand = (r[1], r[0], o)
            else:
                continue
        elif o.kind in ("circle", "arc"):
            cc = np.array(sk.xy(o.pts[0]))
            cand = None
            for p, t in g2.line_circle(a, a + u, cc, o.r):
                if t > L + 1e-6 and (o.kind == "circle" or g2.in_arc(g2.angle_of(cc, p), *sk.arc_angles(o))):
                    if cand is None or t < cand[0]:
                        cand = (t, p, o)
            if cand is None:
                continue
        else:
            continue
        if best is None or cand[0] < best[0]:
            best = cand
    if best is None:
        return False
    p = sk.entities[end_pid]
    p.x, p.y = float(best[1][0]), float(best[1][1])
    try:
        sk.add_constraint("coincident", [end_pid, best[2].id], check=False)
    except SketchError:
        pass
    return True


# ---------------------------------------------------------------------------
# offset (via OCCT wire offsetting, converted back to sketch curves)
# ---------------------------------------------------------------------------

def offset_curves(sk: Sketch, ids, dist: float, frame) -> list[int]:
    """Offset connected curves by ``dist`` (positive = to the left of the
    curve direction / outwards for counter-clockwise loops)."""
    from ..core import kernel as K
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Arc
    edges_ = []
    for cid in ids:
        e = K.curve_edge(sk, sk.entities[cid], frame)
        if e is not None:
            edges_.append(e)
    if not edges_:
        raise SketchError("nothing to offset")
    wire = K.wire_from_edges(edges_)
    closed = False
    try:
        from OCP.BRep import BRep_Tool
        closed = BRep_Tool.IsClosed_s(wire)
    except Exception:
        pass
    mk = BRepOffsetAPI_MakeOffset(wire, GeomAbs_Arc, not closed)
    mk.Perform(float(dist))
    if not mk.IsDone() or mk.Shape().IsNull():
        raise SketchError("offset failed - the distance may collapse the shape")
    out = []
    for ed in K.edges(mk.Shape()):
        out.append(_edge_to_sketch(sk, ed, frame))
    out = [i for i in out if i is not None]
    join_coincident(sk, out, 1e-5)
    return out


def _edge_to_sketch(sk: Sketch, edge, frame):
    from ..core import kernel as K
    info = K.edge_info(edge)
    uv = lambda p: tuple(frame.to_local(np.array(p)))  # noqa: E731
    if info["type"] == "line":
        a, b = uv(info["start"]), uv(info["end"])
        return sk.add_line(a, b) if math.dist(a, b) > TOL else None
    if info["type"] == "circle":
        c = uv(info["center"])
        s_, e_, m_ = uv(info["start"]), uv(info["end"]), uv(info["mid"])
        if math.dist(s_, e_) < 1e-7:
            return sk.add_circle(c, info["radius"])
        ccw = (m_[0] - s_[0]) * (e_[1] - s_[1]) - (m_[1] - s_[1]) * (e_[0] - s_[0]) < 0
        return sk.add_arc(c, s_, e_) if ccw else sk.add_arc(c, e_, s_)
    pts = K.edge_polyline(edge, 0.02)
    uvs = frame.to_local(pts)
    idx = np.linspace(0, len(uvs) - 1, min(10, len(uvs))).astype(int)
    return sk.add_spline([tuple(u) for u in uvs[idx]])


# ---------------------------------------------------------------------------
# DXF
# ---------------------------------------------------------------------------

_DXF_UNITS = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 25.4e-6, 9: 0.0254, 10: 914.4}


def _dxf_pairs(text: str):
    lines = text.splitlines()
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i].strip()), lines[i + 1].strip()
        except ValueError:
            continue


def read_dxf(path: str, scale: float | None = None) -> list[dict]:
    """Parse the 2D entities of an ASCII DXF into simple dicts (mm)."""
    with open(path, "r", encoding="latin-1") as fh:
        pairs = list(_dxf_pairs(fh.read()))
    k = scale
    if k is None:
        k = 1.0
        for i, (c, v) in enumerate(pairs):
            if c == 9 and v == "$INSUNITS" and i + 1 < len(pairs):
                try:
                    k = _DXF_UNITS.get(int(pairs[i + 1][1]), 1.0) or 1.0
                except ValueError:
                    pass
                break
    out: list[dict] = []
    i, n = 0, len(pairs)
    while i < n and not (pairs[i][0] == 2 and pairs[i][1] == "ENTITIES"):
        i += 1
    i += 1
    cur = None

    def flush():
        nonlocal cur
        if cur is not None:
            out.extend(_dxf_entity(cur, k))
        cur = None

    poly = None
    while i < n:
        c, v = pairs[i]
        i += 1
        if c == 0:
            if v == "ENDSEC":
                flush()
                break
            if v == "VERTEX" and poly is not None:
                cur = {"type": "VERTEX", "d": {}}
                flush_vertex = True
                poly["verts"].append(cur["d"])
                continue
            if v == "SEQEND" and poly is not None:
                out.extend(_dxf_polyline(poly, k))
                poly, cur = None, None
                continue
            flush()
            if v == "POLYLINE":
                poly = {"verts": [], "d": {}}
                cur = None
                poly_open = True
                continue
            cur = {"type": v, "d": {}}
            continue
        if cur is not None:
            cur["d"].setdefault(c, []).append(v)
            if cur["type"] == "VERTEX" and poly is not None:
                poly["verts"][-1] = cur["d"]
        elif poly is not None and not poly["verts"]:
            poly["d"].setdefault(c, []).append(v)
    flush()
    return out


def _f(d, code, default=0.0, idx=0):
    try:
        return float(d[code][idx])
    except (KeyError, IndexError, ValueError):
        return default


def _bulge_arc(p0, p1, bulge):
    """Arc for a polyline segment with bulge -> (centre, start, end) CCW or None."""
    if abs(bulge) < 1e-9:
        return None
    a, b = np.array(p0), np.array(p1)
    d = np.linalg.norm(b - a)
    if d < TOL:
        return None
    theta = 4 * math.atan(bulge)
    r = d / (2 * math.sin(theta / 2))
    mid = (a + b) / 2
    nrm = np.array([-(b - a)[1], (b - a)[0]]) / d
    c = mid + nrm * (r * math.cos(theta / 2))
    return (tuple(c), tuple(a), tuple(b)) if bulge > 0 else (tuple(c), tuple(b), tuple(a))


def _dxf_polyline_pts(pts, bulges, closed, k):
    segs = []
    n = len(pts)
    rng = range(n if closed else n - 1)
    for i in rng:
        p0, p1 = pts[i], pts[(i + 1) % n]
        arc = _bulge_arc(p0, p1, bulges[i])
        if arc:
            segs.append({"type": "arc3", "c": arc[0], "s": arc[1], "e": arc[2]})
        elif math.dist(p0, p1) > TOL:
            segs.append({"type": "line", "a": p0, "b": p1})
    return segs


def _dxf_polyline(poly, k):
    pts = [(_f(v, 10) * k, _f(v, 20) * k) for v in poly["verts"] if 10 in v]
    bul = [_f(v, 42) for v in poly["verts"] if 10 in v]
    closed = int(_f(poly["d"], 70)) & 1
    return _dxf_polyline_pts(pts, bul, bool(closed), k)


def _dxf_entity(ent, k):
    t, d = ent["type"], ent["d"]
    if t == "LINE":
        return [{"type": "line", "a": (_f(d, 10) * k, _f(d, 20) * k), "b": (_f(d, 11) * k, _f(d, 21) * k)}]
    if t == "CIRCLE":
        return [{"type": "circle", "c": (_f(d, 10) * k, _f(d, 20) * k), "r": _f(d, 40) * k}]
    if t == "ARC":
        c = np.array([_f(d, 10) * k, _f(d, 20) * k])
        r = _f(d, 40) * k
        a0, a1 = math.radians(_f(d, 50)), math.radians(_f(d, 51))
        s_ = c + r * np.array([math.cos(a0), math.sin(a0)])
        e_ = c + r * np.array([math.cos(a1), math.sin(a1)])
        return [{"type": "arc3", "c": tuple(c), "s": tuple(s_), "e": tuple(e_)}]
    if t == "LWPOLYLINE":
        xs, ys = d.get(10, []), d.get(20, [])
        bs = d.get(42, [])
        pts = [(float(x) * k, float(y) * k) for x, y in zip(xs, ys)]
        # bulge values are listed per vertex only when present; align by vertex order
        bulges = [0.0] * len(pts)
        if bs and len(bs) == len(pts):
            bulges = [float(b) for b in bs]
        return _dxf_polyline_pts(pts, bulges, bool(int(_f(d, 70)) & 1), k)
    if t == "SPLINE":
        fx, fy = d.get(11, []), d.get(21, [])
        if not fx:
            fx, fy = d.get(10, []), d.get(20, [])
        pts = [(float(x) * k, float(y) * k) for x, y in zip(fx, fy)]
        return [{"type": "spline", "pts": pts}] if len(pts) >= 2 else []
    if t == "ELLIPSE":
        c = np.array([_f(d, 10) * k, _f(d, 20) * k])
        m = np.array([_f(d, 11) * k, _f(d, 21) * k])
        ratio = _f(d, 40, 1.0)
        a = np.linalg.norm(m)
        return [{"type": "ellipse", "c": tuple(c), "m": tuple(c + m), "b": float(a * ratio)}]
    return []


def import_entities(sk: Sketch, ents: list[dict], origin=(0.0, 0.0)) -> list[int]:
    """Create sketch curves from parsed 2D entities."""
    ox, oy = origin
    sh = lambda p: (p[0] + ox, p[1] + oy)  # noqa: E731
    ids = []
    for e in ents:
        t = e["type"]
        if t == "line":
            if math.dist(e["a"], e["b"]) > TOL:
                ids.append(sk.add_line(sh(e["a"]), sh(e["b"])))
        elif t == "circle":
            if e["r"] > TOL:
                ids.append(sk.add_circle(sh(e["c"]), e["r"]))
        elif t == "arc3":
            ids.append(sk.add_arc(sh(e["c"]), sh(e["s"]), sh(e["e"])))
        elif t == "spline":
            ids.append(sk.add_spline([sh(p) for p in e["pts"]]))
        elif t == "ellipse":
            ids.append(sk.add_ellipse(sh(e["c"]), sh(e["m"]), e["b"]))
    join_coincident(sk, ids, 1e-5)
    return ids


def write_dxf(sk: Sketch, path: str):
    """Export non-construction curves as a DXF (R12 style, mm)."""
    out = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def add(*kv):
        out.extend(str(x) for x in kv)

    def polyline(pts, closed=False):
        add(0, "POLYLINE", 8, 0, 66, 1, 70, 1 if closed else 0)
        for x, y in pts:
            add(0, "VERTEX", 8, 0, 10, f"{x:.6f}", 20, f"{y:.6f}", 30, "0.0")
        add(0, "SEQEND", 8, 0)

    for e in sk.curves(include_construction=False):
        if e.kind == "line":
            (ax, ay), (bx, by) = sk.xy(e.pts[0]), sk.xy(e.pts[1])
            add(0, "LINE", 8, 0, 10, f"{ax:.6f}", 20, f"{ay:.6f}", 30, 0.0, 11, f"{bx:.6f}", 21, f"{by:.6f}", 31, 0.0)
        elif e.kind == "circle":
            cx, cy = sk.xy(e.pts[0])
            add(0, "CIRCLE", 8, 0, 10, f"{cx:.6f}", 20, f"{cy:.6f}", 30, 0.0, 40, f"{e.r:.6f}")
        elif e.kind == "arc":
            cx, cy = sk.xy(e.pts[0])
            a0, a1 = sk.arc_angles(e)
            add(0, "ARC", 8, 0, 10, f"{cx:.6f}", 20, f"{cy:.6f}", 30, 0.0, 40, f"{e.r:.6f}",
                50, f"{math.degrees(a0) % 360:.6f}", 51, f"{math.degrees(a1) % 360:.6f}")
        else:  # spline / ellipse / text outlines as polylines
            for pl in sk.polylines(e):
                if len(pl) > 1:
                    polyline(pl)
    out += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", encoding="latin-1") as fh:
        fh.write("\n".join(out) + "\n")


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def _parse_transform(txt: str) -> np.ndarray:
    m = np.eye(3)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", txt or ""):
        a = [float(x) for x in re.split(r"[,\s]+", args.strip()) if x]
        t = np.eye(3)
        if name == "matrix" and len(a) == 6:
            t = np.array([[a[0], a[2], a[4]], [a[1], a[3], a[5]], [0, 0, 1]])
        elif name == "translate":
            t[0, 2], t[1, 2] = a[0], (a[1] if len(a) > 1 else 0)
        elif name == "scale":
            t[0, 0], t[1, 1] = a[0], (a[1] if len(a) > 1 else a[0])
        elif name == "rotate":
            r = math.radians(a[0])
            t = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
            if len(a) == 3:
                t = np.array([[1, 0, a[1]], [0, 1, a[2]], [0, 0, 1]]) @ t @ np.array([[1, 0, -a[1]], [0, 1, -a[2]], [0, 0, 1]])
        m = m @ t
    return m


def _length(v: str | None, default=None):
    if v is None:
        return default
    m = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)\s*([a-z%]*)", v)
    if not m:
        return default
    unit = {"": 25.4 / 96, "px": 25.4 / 96, "mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6}
    return float(m.group(1)) * unit.get(m.group(2), 25.4 / 96)


def _bezier(p0, c1, c2, p1, n=12):
    t = np.linspace(0, 1, n + 1)[:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1


def _arc_points(p0, rx, ry, phi, fa, fs, p1, n=16):
    """SVG elliptical arc -> sampled points (endpoint to centre conversion)."""
    if rx == 0 or ry == 0:
        return np.array([p0, p1])
    cp, sp_ = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p, y1p = cp * dx + sp_ * dy, -sp_ * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp_ * cyp + (p0[0] + p1[0]) / 2
    cy = sp_ * cxp + cp * cyp + (p0[1] + p1[1]) / 2
    ang = lambda ux, uy, vx, vy: math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)  # noqa: E731
    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dth > 0:
        dth -= 2 * math.pi
    elif fs and dth < 0:
        dth += 2 * math.pi
    t = th1 + np.linspace(0, dth, n + 1)
    x = cp * rx * np.cos(t) - sp_ * ry * np.sin(t) + cx
    y = sp_ * rx * np.cos(t) + cp * ry * np.sin(t) + cy
    return np.column_stack([x, y])


def _path_subpaths(d: str):
    """Yield (points Nx2, closed, has_curve) for each sub-path of an SVG path."""
    toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    i, cmd = 0, None
    cur = np.zeros(2)
    start = np.zeros(2)
    pts: list = []
    closed = False
    curved = False
    last_c = None
    last_q = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flush():
        nonlocal pts, closed, curved
        if len(pts) > 1:
            yield np.array(pts), closed, curved
        pts, closed, curved = [], False, False

    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                closed = True
                cur = start.copy()
                yield from flush()
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            yield from flush()
            p = np.array([num(), num()]) + (cur if rel else 0)
            cur = start = p
            pts = [tuple(p)]
            cmd = "l" if rel else "L"
            continue
        if not pts:
            pts = [tuple(cur)]
        if c == "L":
            cur = np.array([num(), num()]) + (cur if rel else 0)
            pts.append(tuple(cur))
        elif c == "H":
            x = num() + (cur[0] if rel else 0)
            cur = np.array([x, cur[1]])
            pts.append(tuple(cur))
        elif c == "V":
            y = num() + (cur[1] if rel else 0)
            cur = np.array([cur[0], y])
            pts.append(tuple(cur))
        elif c in ("C", "S"):
            if c == "C":
                c1 = np.array([num(), num()]) + (cur if rel else 0)
            else:
                c1 = 2 * cur - last_c if last_c is not None else cur.copy()
            c2 = np.array([num(), num()]) + (cur if rel else 0)
            p1 = np.array([num(), num()]) + (cur if rel else 0)
            seg = _bezier(cur, c1, c2, p1)
            pts.extend(tuple(q) for q in seg[1:])
            last_c, cur, curved = c2, p1, True
            continue
        elif c in ("Q", "T"):
            if c == "Q":
                q1 = np.array([num(), num()]) + (cur if rel else 0)
            else:
                q1 = 2 * cur - last_q if last_q is not None else cur.copy()
            p1 = np.array([num(), num()]) + (cur if rel else 0)
            seg = _bezier(cur, cur + 2 / 3 * (q1 - cur), p1 + 2 / 3 * (q1 - p1), p1)
            pts.extend(tuple(q) for q in seg[1:])
            last_q, cur, curved = q1, p1, True
            continue
        elif c == "A":
            rx, ry, phi, fa, fs = num(), num(), num(), int(num()), int(num())
            p1 = np.array([num(), num()]) + (cur if rel else 0)
            seg = _arc_points(cur, rx, ry, phi, fa, fs, p1)
            pts.extend(tuple(q) for q in seg[1:])
            cur, curved = p1, True
        else:
            i += 1
        last_c = last_q = None
    yield from flush()


def read_svg(path: str) -> list[dict]:
    """Parse an SVG into simple entity dicts (mm, y up)."""
    root = ET.parse(path).getroot()
    strip = lambda t: t.split("}")[-1]  # noqa: E731
    k = 25.4 / 96
    vb = root.get("viewBox")
    w = _length(root.get("width"))
    if vb and w:
        vbw = float(re.split(r"[,\s]+", vb.strip())[2])
        if vbw > 0:
            k = w / vbw
    ents: list[dict] = []

    def walk(el, m):
        m = m @ _parse_transform(el.get("transform"))
        t = strip(el.tag)
        P = lambda x, y: tuple((m @ np.array([x, y, 1.0]))[:2] * np.array([k, -k]))  # noqa: E731
        f = lambda key: float(el.get(key, 0) or 0)  # noqa: E731
        if t == "line":
            ents.append({"type": "line", "a": P(f("x1"), f("y1")), "b": P(f("x2"), f("y2"))})
        elif t in ("polyline", "polygon"):
            nums = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", el.get("points", ""))]
            pts = [P(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            if t == "polygon" and pts:
                pts.append(pts[0])
            ents.extend([{"type": "line", "a": a, "b": b} for a, b in zip(pts[:-1], pts[1:])])
        elif t == "rect":
            x, y, w_, h = f("x"), f("y"), f("width"), f("height")
            c = [P(x, y), P(x + w_, y), P(x + w_, y + h), P(x, y + h)]
            ents.extend([{"type": "line", "a": c[i], "b": c[(i + 1) % 4]} for i in range(4)])
        elif t == "circle":
            sc = math.sqrt(abs(np.linalg.det(m[:2, :2]))) * k
            ents.append({"type": "circle", "c": P(f("cx"), f("cy")), "r": f("r") * sc})
        elif t == "ellipse":
            cx, cy, rx, ry = f("cx"), f("cy"), f("rx"), f("ry")
            ents.append({"type": "ellipse", "c": P(cx, cy), "m": P(cx + rx, cy),
                         "b": ry * math.sqrt(abs(np.linalg.det(m[:2, :2]))) * k})
        elif t == "path":
            for pts, closed, curved in _path_subpaths(el.get("d", "")):
                q = [P(x, y) for x, y in pts]
                if curved and len(q) > 3:
                    idx = np.unique(np.linspace(0, len(q) - 1, min(len(q), 24)).astype(int))
                    sel = [q[j] for j in idx]
                    ents.append({"type": "spline", "pts": sel})
                    if closed and math.dist(sel[0], sel[-1]) > TOL:
                        ents.append({"type": "line", "a": sel[-1], "b": sel[0]})
                else:
                    if closed and math.dist(q[0], q[-1]) > TOL:
                        q.append(q[0])
                    ents.extend([{"type": "line", "a": a, "b": b} for a, b in zip(q[:-1], q[1:]) if math.dist(a, b) > TOL])
        for ch in el:
            walk(ch, m)

    walk(root, np.eye(3))
    return ents


def import_2d_file(sk: Sketch, path: str, origin=(0.0, 0.0)) -> list[int]:
    ext = path.lower().rsplit(".", 1)[-1]
    if ext == "dxf":
        ents = read_dxf(path)
    elif ext == "svg":
        ents = read_svg(path)
    else:
        raise SketchError("unsupported file type (use .dxf or .svg)")
    if not ents:
        raise SketchError("no drawable geometry found in the file")
    ids = import_entities(sk, ents, origin)
    return ids
