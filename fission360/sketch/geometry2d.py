"""2D geometry helpers for sketch editing (intersections, projections, trim)."""
from __future__ import annotations

import math

import numpy as np


def seg_param(p, a, b):
    d = np.subtract(b, a)
    L2 = float(np.dot(d, d))
    if L2 < 1e-18:
        return 0.0
    return float(np.dot(np.subtract(p, a), d) / L2)


def closest_on_segment(p, a, b):
    t = min(1.0, max(0.0, seg_param(p, a, b)))
    return np.add(a, np.subtract(b, a) * t), t


def angle_of(c, p):
    return math.atan2(p[1] - c[1], p[0] - c[0])


def in_arc(a, a0, a1):
    """Is angle ``a`` inside the CCW arc a0 -> a1 (a1 > a0)?"""
    a = (a - a0) % (2 * math.pi)
    return a <= (a1 - a0) + 1e-9


def line_line(a, b, c, d):
    """Intersection of infinite lines ab and cd -> (point, t on ab, u on cd)."""
    r = np.subtract(b, a)
    s = np.subtract(d, c)
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    q = np.subtract(c, a)
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    return np.add(a, r * t), t, u


def line_circle(a, b, c, r):
    """Intersections of infinite line ab with circle -> list of (point, t)."""
    d = np.subtract(b, a)
    f = np.subtract(a, c)
    A = float(np.dot(d, d))
    if A < 1e-18:
        return []
    B = 2 * float(np.dot(f, d))
    C = float(np.dot(f, f)) - r * r
    disc = B * B - 4 * A * C
    if disc < -1e-12:
        return []
    disc = math.sqrt(max(disc, 0.0))
    out = []
    for t in ((-B - disc) / (2 * A), (-B + disc) / (2 * A)):
        out.append((np.add(a, d * t), t))
    return out


def circle_circle(c1, r1, c2, r2):
    d = math.dist(c1, c2)
    if d < 1e-12 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    ex = np.subtract(c2, c1) / d
    m = np.add(c1, ex * a)
    perp = np.array([-ex[1], ex[0]])
    return [m + perp * h, m - perp * h] if h > 1e-12 else [m]


def curve_intersections(sketch, e, others):
    """Points where curve ``e`` meets other curves, as parameters along e.

    Lines: t in (0,1). Circles/arcs: angles.  Returns sorted list of
    (param, point).
    """
    out = []
    if e.kind == "line":
        a, b = sketch.xy(e.pts[0]), sketch.xy(e.pts[1])
        for o in others:
            if o.kind == "line":
                c, d = sketch.xy(o.pts[0]), sketch.xy(o.pts[1])
                r = line_line(a, b, c, d)
                if r and 1e-9 < r[1] < 1 - 1e-9 and -1e-9 <= r[2] <= 1 + 1e-9:
                    out.append((r[1], r[0]))
            elif o.kind in ("circle", "arc"):
                cc = sketch.xy(o.pts[0])
                for p, t in line_circle(a, b, cc, o.r):
                    if 1e-9 < t < 1 - 1e-9 and (o.kind == "circle" or in_arc(angle_of(cc, p), *sketch.arc_angles(o))):
                        out.append((t, p))
    elif e.kind in ("circle", "arc"):
        c = sketch.xy(e.pts[0])
        for o in others:
            pts = []
            if o.kind == "line":
                a, b = sketch.xy(o.pts[0]), sketch.xy(o.pts[1])
                pts = [p for p, t in line_circle(a, b, c, e.r) if -1e-9 <= t <= 1 + 1e-9]
            elif o.kind in ("circle", "arc"):
                cc = sketch.xy(o.pts[0])
                pts = [p for p in circle_circle(c, e.r, cc, o.r)
                       if o.kind == "circle" or in_arc(angle_of(cc, p), *sketch.arc_angles(o))]
            for p in pts:
                out.append((angle_of(c, p), p))
    out.sort(key=lambda t: t[0])
    return out


def nearest_on_curve(sketch, e, p):
    """Closest point on a sketch curve to p -> (point, distance)."""
    if e.kind == "line":
        q, _ = closest_on_segment(p, sketch.xy(e.pts[0]), sketch.xy(e.pts[1]))
        return q, math.dist(q, p)
    if e.kind in ("circle", "arc"):
        c = np.array(sketch.xy(e.pts[0]))
        d = np.subtract(p, c)
        n = np.linalg.norm(d)
        q = c + (d / n * e.r if n > 1e-12 else np.array([e.r, 0]))
        if e.kind == "arc" and not in_arc(angle_of(c, q), *sketch.arc_angles(e)):
            ends = [np.array(sketch.xy(e.pts[1])), np.array(sketch.xy(e.pts[2]))]
            q = min(ends, key=lambda t: math.dist(t, p))
        return q, math.dist(q, p)
    if e.kind in ("spline", "ellipse", "text"):
        best = (None, 1e18)
        for pl in sketch.polylines(e):
            for a, b in zip(pl[:-1], pl[1:]):
                q, _ = closest_on_segment(p, a, b)
                dd = math.dist(q, p)
                if dd < best[1]:
                    best = (q, dd)
        return best
    return np.array(p), 1e18
