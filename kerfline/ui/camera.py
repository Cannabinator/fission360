"""Orbit camera with perspective/orthographic projection (Z-up world)."""
from __future__ import annotations

import math

import numpy as np


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_axis(axis, angle):
    axis = np.asarray(axis, float)
    axis = axis / (np.linalg.norm(axis) or 1)
    s = math.sin(angle / 2)
    return np.array([math.cos(angle / 2), *(axis * s)])


def quat_matrix(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def matrix_quat(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    i = int(np.argmax(np.diag(m)))
    if i == 0:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    if i == 1:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])


def slerp(a, b, t):
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + t * (b - a)
        return r / np.linalg.norm(r)
    th = math.acos(d)
    return (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)


def look_rotation(view_dir, up):
    """Camera-to-world rotation for a camera looking along ``view_dir``."""
    f = np.asarray(view_dir, float)
    f = f / np.linalg.norm(f)
    up = np.asarray(up, float)
    if abs(np.dot(f, up / np.linalg.norm(up))) > 0.999:
        up = np.array([0, 1.0, 0]) if abs(f[1]) < 0.9 else np.array([1.0, 0, 0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    # camera looks down -Z in its own frame
    return np.column_stack([r, u, -f])


STANDARD_VIEWS = {
    "Front": ([0, 1, 0], [0, 0, 1]), "Back": ([0, -1, 0], [0, 0, 1]),
    "Top": ([0, 0, -1], [0, 1, 0]), "Bottom": ([0, 0, 1], [0, -1, 0]),
    "Left": ([1, 0, 0], [0, 0, 1]), "Right": ([-1, 0, 0], [0, 0, 1]),
    "Home": ([-1, 1, -0.8], [0, 0, 1]),
}


class Camera:
    def __init__(self):
        self.target = np.zeros(3)
        self.distance = 250.0
        self.rot = matrix_quat(look_rotation(*STANDARD_VIEWS["Home"]))
        self.fov = 35.0
        self.ortho = False
        self.width = 800
        self.height = 600
        self._anim = None

    # ------------------------------------------------------------------ matrices
    def rotation(self) -> np.ndarray:
        return quat_matrix(self.rot)

    def eye(self) -> np.ndarray:
        R = self.rotation()
        return self.target + R[:, 2] * self.distance

    def forward(self) -> np.ndarray:
        return -self.rotation()[:, 2]

    def view_matrix(self) -> np.ndarray:
        R = self.rotation()
        m = np.eye(4)
        m[:3, :3] = R.T
        m[:3, 3] = -R.T @ self.eye()
        return m

    def ortho_half_height(self) -> float:
        return self.distance * math.tan(math.radians(self.fov) / 2)

    def near_far(self, scene_radius: float = 1000.0):
        far = self.distance + scene_radius * 4 + 1000
        near = max(far * 1e-5, 0.01) if not self.ortho else -far
        return near, far

    def proj_matrix(self, scene_radius: float = 1000.0) -> np.ndarray:
        aspect = self.width / max(1, self.height)
        n, f = self.near_far(scene_radius)
        if self.ortho:
            h = self.ortho_half_height()
            w = h * aspect
            m = np.eye(4)
            m[0, 0], m[1, 1], m[2, 2] = 1 / w, 1 / h, -2 / (f - n)
            m[2, 3] = -(f + n) / (f - n)
            return m
        t = 1 / math.tan(math.radians(self.fov) / 2)
        m = np.zeros((4, 4))
        m[0, 0], m[1, 1] = t / aspect, t
        m[2, 2], m[2, 3] = (f + n) / (n - f), 2 * f * n / (n - f)
        m[3, 2] = -1
        return m

    def mvp(self, scene_radius=1000.0) -> np.ndarray:
        return self.proj_matrix(scene_radius) @ self.view_matrix()

    # ------------------------------------------------------------------ projection helpers
    def project(self, pts, scene_radius=1000.0) -> np.ndarray:
        """World -> screen pixels (x right, y down). Returns (N,3) with depth."""
        pts = np.atleast_2d(np.asarray(pts, float))
        h = np.hstack([pts, np.ones((len(pts), 1))]) @ self.mvp(scene_radius).T
        w = h[:, 3:4]
        w[np.abs(w) < 1e-12] = 1e-12
        ndc = h[:, :3] / w
        x = (ndc[:, 0] + 1) * 0.5 * self.width
        y = (1 - ndc[:, 1]) * 0.5 * self.height
        return np.column_stack([x, y, ndc[:, 2]])

    def ray(self, sx, sy) -> tuple[np.ndarray, np.ndarray]:
        """World-space ray through a screen pixel."""
        nx = 2 * sx / max(1, self.width) - 1
        ny = 1 - 2 * sy / max(1, self.height)
        R = self.rotation()
        aspect = self.width / max(1, self.height)
        if self.ortho:
            h = self.ortho_half_height()
            origin = self.eye() + R[:, 0] * nx * h * aspect + R[:, 1] * ny * h
            return origin - self.forward() * self.distance * 10, self.forward()
        t = math.tan(math.radians(self.fov) / 2)
        d = -R[:, 2] + R[:, 0] * nx * t * aspect + R[:, 1] * ny * t
        return self.eye(), d / np.linalg.norm(d)

    def pixel_size_at(self, point) -> float:
        """World units per pixel at a given point (for constant-size glyphs)."""
        if self.ortho:
            return 2 * self.ortho_half_height() / max(1, self.height)
        depth = max(1e-6, float(np.dot(np.asarray(point) - self.eye(), self.forward())))
        return 2 * depth * math.tan(math.radians(self.fov) / 2) / max(1, self.height)

    def unproject_depth(self, sx, sy, depth01, scene_radius=1000.0) -> np.ndarray:
        """Screen pixel + depth-buffer value -> world point."""
        nx = 2 * sx / max(1, self.width) - 1
        ny = 1 - 2 * sy / max(1, self.height)
        nz = depth01 * 2 - 1
        inv = np.linalg.inv(self.mvp(scene_radius))
        p = inv @ np.array([nx, ny, nz, 1.0])
        return p[:3] / p[3]

    # ------------------------------------------------------------------ navigation
    def orbit(self, dx, dy, pivot=None):
        """Turntable orbit: yaw around world Z, pitch around camera right."""
        R = self.rotation()
        yaw = quat_axis([0, 0, 1], -dx * 0.008)
        pitch = quat_axis(R[:, 0], -dy * 0.008)
        q = quat_mul(yaw, quat_mul(pitch, self.rot))
        q /= np.linalg.norm(q)
        if pivot is not None:
            Rn = quat_matrix(q)
            Rd = Rn @ R.T
            self.target = pivot + Rd @ (self.target - pivot)
            self.rot = q
        else:
            self.rot = q

    def pan(self, dx, dy, ref_point=None):
        R = self.rotation()
        s = self.pixel_size_at(ref_point if ref_point is not None else self.target)
        self.target = self.target - R[:, 0] * dx * s + R[:, 1] * dy * s

    def zoom(self, factor, sx=None, sy=None, point=None):
        """Zoom by ``factor`` (<1 zooms in) towards a screen location."""
        if point is None and sx is not None:
            o, d = self.ray(sx, sy)
            # aim at the plane through the target perpendicular to the view
            t = np.dot(self.target - o, self.forward()) / max(1e-9, np.dot(d, self.forward()))
            point = o + d * t
        old = self.distance
        self.distance = float(np.clip(self.distance * factor, 1e-3, 1e7))
        if point is not None:
            k = 1 - self.distance / old
            self.target = self.target + (np.asarray(point) - self.target) * k

    def fit(self, lo, hi, animate_to=None):
        lo, hi = np.asarray(lo, float), np.asarray(hi, float)
        c = (lo + hi) / 2
        r = max(float(np.linalg.norm(hi - lo)) / 2, 1.0)
        dist = r / math.sin(math.radians(self.fov) / 2) * 1.05
        aspect = self.width / max(1, self.height)
        if aspect < 1:
            dist /= aspect
        return c, dist

    def set_view(self, view_dir, up, target=None, distance=None):
        q = matrix_quat(look_rotation(view_dir, up))
        self.start_animation(q, target if target is not None else self.target,
                             distance if distance is not None else self.distance)

    def start_animation(self, rot, target, distance, duration=0.35):
        import time
        self._anim = (time.perf_counter(), duration, self.rot.copy(), self.target.copy(), self.distance,
                      np.asarray(rot, float), np.asarray(target, float), float(distance))

    def step_animation(self) -> bool:
        """Advance an in-flight view animation. Returns True while animating."""
        if self._anim is None:
            return False
        import time
        t0, dur, r0, c0, d0, r1, c1, d1 = self._anim
        t = min(1.0, (time.perf_counter() - t0) / dur)
        e = t * t * (3 - 2 * t)  # smoothstep
        self.rot = slerp(r0, r1, e)
        self.target = c0 + (c1 - c0) * e
        self.distance = d0 * (d1 / d0) ** e if d0 > 0 and d1 > 0 else d0 + (d1 - d0) * e
        if t >= 1.0:
            self._anim = None
            return False
        return True
