"""Geometric constraint solver for 2D sketches.

Design (similar in spirit to SolveSpace / D-Cubed style numeric solvers):

* Unknowns are point coordinates and circle radii.
* Every constraint contributes one or more scalar residual equations.
* We solve ``r(x) = 0`` with damped Gauss-Newton where each step is the
  **minimum-norm** least-squares solution (SVD based).  Minimum-norm steps are
  what make interactive dragging feel natural: geometry that is not pinned
  by constraints moves as little as possible.
* Dragged variables are column-scaled so the solver prefers moving
  everything else (the grabbed point "sticks" to the cursor).
* Degrees of freedom are reported from the Jacobian rank; per-variable
  freedom is derived from the Jacobian null space so the UI can colour fully
  constrained geometry differently (blue = free, black = constrained).

Each residual only touches a handful of variables, so the Jacobian is
assembled from local central differences -- cheap and robust for the few
hundred unknowns that typical sketches have.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Equation:
    vars: list[int]          # indices into the global variable vector
    fn: object               # callable(vals: np.ndarray) -> float | sequence
    count: int = 1           # number of scalar residuals
    tag: object = None       # constraint id (for diagnostics)


@dataclass
class SolveResult:
    ok: bool
    iterations: int
    residual: float
    dof: int
    rank: int
    free_vars: np.ndarray    # bool mask: variable still has freedom
    redundant: bool


def _eval(eqs: list[Equation], x: np.ndarray, m: int) -> np.ndarray:
    r = np.empty(m)
    k = 0
    for e in eqs:
        v = e.fn(x[e.vars])
        if e.count == 1:
            r[k] = v
        else:
            r[k:k + e.count] = v
        k += e.count
    return r


def _jacobian(eqs: list[Equation], x: np.ndarray, m: int, n: int) -> np.ndarray:
    J = np.zeros((m, n))
    k = 0
    for e in eqs:
        vals = x[e.vars].copy()
        for j, gi in enumerate(e.vars):
            h = 1e-7 * max(1.0, abs(vals[j]))
            old = vals[j]
            vals[j] = old + h
            fp = np.atleast_1d(e.fn(vals))
            vals[j] = old - h
            fm = np.atleast_1d(e.fn(vals))
            vals[j] = old
            J[k:k + e.count, gi] += (fp - fm) / (2 * h)
        k += e.count
    return J


def solve(eqs: list[Equation], x0: np.ndarray, weights: np.ndarray | None = None,
          max_iter: int = 60, tol: float = 1e-9, analyse: bool = True) -> tuple[np.ndarray, SolveResult]:
    """Solve ``eqs`` starting at ``x0``.

    ``weights`` (per-variable, default 1) scale how willing the solver is to
    move a variable: small weight -> variable moves reluctantly.
    """
    n = len(x0)
    m = sum(e.count for e in eqs)
    x = np.array(x0, dtype=float)
    if weights is None:
        weights = np.ones(n)
    if m == 0 or n == 0:
        return x, SolveResult(True, 0, 0.0, n, 0, np.ones(n, bool), False)

    r = _eval(eqs, x, m)
    err = float(np.linalg.norm(r))
    it = 0
    W = weights
    while err > tol and it < max_iter:
        it += 1
        J = _jacobian(eqs, x, m, n)
        Js = J * W  # column scaling
        dz, *_ = np.linalg.lstsq(Js, -r, rcond=1e-10)
        dx = dz * W
        # Backtracking line search keeps the solver stable far from solution
        step = 1.0
        while step > 1e-4:
            xn = x + step * dx
            rn = _eval(eqs, xn, m)
            en = float(np.linalg.norm(rn))
            if en < err or en < tol:
                break
            step *= 0.5
        else:
            break  # no progress
        x, r, err = xn, rn, en

    ok = err <= max(tol * 10, 1e-7)
    if not analyse:
        return x, SolveResult(ok, it, err, -1, -1, np.ones(n, bool), False)

    J = _jacobian(eqs, x, m, n)
    if J.size:
        U, s, Vt = np.linalg.svd(J, full_matrices=True)
        smax = s[0] if s.size else 0.0
        rank = int(np.sum(s > max(1e-8, smax * 1e-9)))
        null = Vt[rank:].T  # n x (n-rank)
        free = np.linalg.norm(null, axis=1) > 1e-6 if null.size else np.zeros(n, bool)
    else:
        rank, free = 0, np.ones(n, bool)
    return x, SolveResult(ok, it, err, n - rank, rank, free, rank < m)


# ---------------------------------------------------------------------------
# Residual builders
# ---------------------------------------------------------------------------

def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def r_coincident(v):
    return (v[0] - v[2], v[1] - v[3])


def r_point_on_line(v):
    px, py, ax, ay, bx, by = v
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1e-12
    return ((px - ax) * dy - (py - ay) * dx) / L


def r_point_on_circle(v):
    px, py, cx, cy, r = v
    return math.hypot(px - cx, py - cy) - r


def r_point_on_arc(v):  # arc given by center & start point (radius implicit)
    px, py, cx, cy, sx, sy = v
    return math.hypot(px - cx, py - cy) - math.hypot(sx - cx, sy - cy)


def r_horizontal(v):
    return v[1] - v[3]


def r_vertical(v):
    return v[0] - v[2]


def _dirs(v):
    d1 = (v[2] - v[0], v[3] - v[1])
    d2 = (v[6] - v[4], v[7] - v[5])
    l1 = math.hypot(*d1) or 1e-12
    l2 = math.hypot(*d2) or 1e-12
    return d1, d2, l1, l2


def r_parallel(v):
    d1, d2, l1, l2 = _dirs(v)
    return (d1[0] * d2[1] - d1[1] * d2[0]) / (l1 * l2)


def r_perpendicular(v):
    d1, d2, l1, l2 = _dirs(v)
    return (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)


def r_equal_length(v):
    d1, d2, l1, l2 = _dirs(v)
    return l1 - l2


def r_equal(v):
    return v[0] - v[1]


def make_angle(target_fn, sign: float = 1.0):
    def f(v):
        d1, d2, _, _ = _dirs(v)
        a = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
        return _wrap(sign * a - target_fn())
    return f


def make_distance(target_fn):
    def f(v):
        return math.hypot(v[0] - v[2], v[1] - v[3]) - target_fn()
    return f


def make_hdistance(target_fn):
    def f(v):
        return abs(v[2] - v[0]) - target_fn()
    return f


def make_vdistance(target_fn):
    def f(v):
        return abs(v[3] - v[1]) - target_fn()
    return f


def make_point_line_distance(target_fn):
    def f(v):
        return abs(r_point_on_line(v)) - target_fn()
    return f


def make_value(target_fn, scale: float = 1.0):
    def f(v):
        return v[0] * scale - target_fn()
    return f


def make_fix(x, y):
    def f(v):
        return (v[0] - x, v[1] - y)
    return f


def make_tangent_line_circle(sign):
    # signed distance from centre to line equals +/- radius
    def f(v):
        ax, ay, bx, by, cx, cy, r = v
        return sign * r_point_on_line((cx, cy, ax, ay, bx, by)) - r
    return f


def make_tangent_circle_circle(internal: bool):
    def f(v):
        c1x, c1y, r1, c2x, c2y, r2 = v
        d = math.hypot(c1x - c2x, c1y - c2y)
        return d - abs(r1 - r2) if internal else d - (r1 + r2)
    return f


def r_midpoint(v):
    px, py, ax, ay, bx, by = v
    return (px - (ax + bx) / 2, py - (ay + by) / 2)


def r_symmetric(v):
    # p, q symmetric about line a-b
    px, py, qx, qy, ax, ay, bx, by = v
    mx, my = (px + qx) / 2, (py + qy) / 2
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1e-12
    on_line = ((mx - ax) * dy - (my - ay) * dx) / L
    perp = ((qx - px) * dx + (qy - py) * dy) / L
    return (on_line, perp)


def r_arc_radius(v):  # center, start, end -> |s-c| == |e-c|
    cx, cy, sx, sy, ex, ey = v
    return math.hypot(sx - cx, sy - cy) - math.hypot(ex - cx, ey - cy)
