"""3D viewport: rendering, navigation, picking, hover & selection.

Navigation follows Fusion 360 defaults:
  * middle drag            pan
  * shift + middle drag    orbit (also: right drag, or alt + left drag)
  * wheel                  zoom about the cursor
  * double middle click    fit all
Orbit pivots around the geometry under the cursor.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from OpenGL import GL
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF,
                           QSurfaceFormat)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..core import kernel as K
from . import gl as G
from .camera import STANDARD_VIEWS, Camera, look_rotation, matrix_quat
from .theme import THEME


@dataclass(frozen=True)
class Pick:
    kind: str            # face | edge | vertex | profile | curve | spoint | plane | axis | origin
    key: str             # body id / sketch feature id / plane name
    index: int = -1      # sub-element index (face index, entity id, ...)
    point: tuple = field(default=(0.0, 0.0, 0.0), compare=False, hash=False)


@dataclass
class Manipulator:
    """In-canvas drag handle (Fusion's distance arrows).

    The handle sits at ``origin + direction * value``; dragging it projects
    the cursor ray onto the handle's axis and reports the new value.
    """
    origin: np.ndarray
    direction: np.ndarray
    value: float
    on_drag: object                 # callable(new_value, final: bool)
    label: str = ""
    kind: str = "arrow"             # arrow | dot
    min_value: float | None = None


KIND_PRIORITY = {"spoint": 0, "vertex": 1, "curve": 2, "edge": 3, "axis": 4, "origin": 2, "profile": 6,
                 "face": 7, "plane": 8}


class PickRegistry:
    def __init__(self):
        self.ranges: list[tuple[int, int, str, str]] = []
        self.next = 1

    def clear(self):
        self.ranges.clear()
        self.next = 1

    def alloc(self, n: int, kind: str, key: str) -> int:
        """Reserve ids [base+1, base+n]; element i has id base + i + 1.

        Shader output is ``u_base + local`` where local ids are 1-based for
        lines/points and 0-based for mesh faces; callers pass base accordingly.
        """
        base = self.next
        self.ranges.append((base, base + max(n, 1), kind, key))
        self.next = base + max(n, 1) + 1
        return base

    def lookup(self, pid: int):
        for s, e, kind, key in self.ranges:
            if s <= pid < e:
                return kind, key, pid - s
        return None


def _qc(rgb, a=1.0):
    return QColor.fromRgbF(rgb[0], rgb[1], rgb[2], a)


class Viewport(QOpenGLWidget):
    hover_changed = Signal(object)
    selection_changed = Signal()
    context_requested = Signal(object)      # QPoint (global)
    status = Signal(str)
    double_clicked = Signal(object)         # Pick or None

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setSamples(4)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)

        self.doc = None
        self.cam = Camera()
        self.r: G.Renderer | None = None
        self.gpu: dict[str, tuple[int, G.BodyGPU]] = {}
        self.reg = PickRegistry()
        self.pick_dirty = True
        self.scene_dirty = True
        self.body_ids: dict[str, tuple[int, int, int]] = {}   # bid -> (face base, edge base, vert base)

        self.selection: list[Pick] = []
        self.hover: Pick | None = None
        self.filter: set[str] | None = None     # None = default (faces, edges, bodies, curves, profiles)
        self.tool = None                          # active interaction tool (sketch tools / commands)
        self.sketch_ctx = None                    # (fid, sketch, frame) while editing a sketch
        self.show_profiles_for: set[str] = set()  # sketch ids whose profiles are pickable/shaded
        self.preview_shapes: list = []           # (shape, rgb, alpha) feature previews
        self._preview_gpu: list = []
        self.hidden_bodies: set[str] = set()      # temporarily hidden (e.g. while editing)
        self.display_state = None                 # model state override (feature editing)
        self.show_points = False                  # show points of all sketches (hole command)

        self.style = "shaded_edges"              # shaded | shaded_edges | wireframe | hidden_edges
        self.show_grid = True
        self.show_origin = False
        self.section: tuple | None = None        # (origin, normal) clip plane
        self.sketch_batch = G.Batch()
        self.sketch_pts = G.Batch()
        self.sketch_construction = G.Batch()
        self.profile_batch = G.Batch()
        self.plane_batch = G.Batch()
        self.plane_lines = G.Batch()
        self.grid = G.Batch()
        self.grid_minor = G.Batch()
        self.tool_lines = G.Batch()
        self.tool_points = G.Batch()
        self._grid_key = None
        self._sketch_elem: dict[int, tuple] = {}   # pick id -> descriptor
        self._profiles_cache: dict[str, list] = {}  # sketch id -> profile faces as displayed
        self._plane_list: list = []
        self._press = None
        self._last = None
        self._nav = None
        self._pivot = None
        self._scene_radius = 500.0
        self._cube_hover = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.fps_ms = 0.0
        self.labels: list = []                    # overlay labels from tools: (world pt, text, color)
        self.manipulators: list[Manipulator] = []
        self._manip_hover = None
        self._manip_drag = None
        self._box = None                          # rubber-band selection (x0, y0, x1, y1)
        self._box_anchor = None
        self.highlight_bodies: set[str] = set()   # e.g. bodies of the hovered timeline feature
        self.show_dimensions = True
        self.show_constraints = True
        self.hide_profiles = False
        self._cube_press = None
        self._moved = False

    # ------------------------------------------------------------------ public API
    @property
    def vstate(self):
        if self.display_state is not None:
            return self.display_state
        from ..core.document import ModelState
        return self.doc.state if self.doc is not None else ModelState()

    def set_document(self, doc):
        self.doc = doc
        self.selection.clear()
        self.hover = None
        self.scene_dirty = True
        self.update()

    def invalidate(self):
        self.scene_dirty = True
        self.pick_dirty = True
        self.update()

    def set_filter(self, kinds):
        self.filter = set(kinds) if kinds is not None else None
        self.hover = None
        self.pick_dirty = True
        self.update()

    def clear_selection(self):
        if self.selection:
            self.selection.clear()
            self.selection_changed.emit()
            self.update()

    def set_selection(self, picks):
        self.selection = list(picks)
        self.selection_changed.emit()
        self.update()

    def accepts(self, kind: str) -> bool:
        if self.filter is None:
            if self.sketch_ctx is not None:
                return kind in ("curve", "spoint", "origin", "profile")
            return kind in ("face", "edge", "profile", "curve", "plane", "axis")
        return kind in self.filter

    # ------------------------------------------------------------------ GL lifecycle
    def initializeGL(self):
        self.r = G.Renderer()
        self.gpu.clear()
        self.scene_dirty = True

    def resizeGL(self, w, h):
        self.cam.width, self.cam.height = w, h
        self.pick_dirty = True

    def _dpr(self):
        return self.devicePixelRatioF()

    def _tick(self):
        if self.cam.step_animation():
            self.pick_dirty = True
            self.update()
        else:
            self._timer.stop()
            self.pick_dirty = True
            self.update()

    def animate_view(self, view_dir, up, fit=False):
        target, dist = self.cam.target, self.cam.distance
        if fit:
            lo, hi = self.scene_bounds()
            target, dist = self.cam.fit(lo, hi)
        self.cam.set_view(view_dir, up, target, dist)
        self._timer.start()

    def fit_all(self, animate=True):
        lo, hi = self.scene_bounds()
        c, d = self.cam.fit(lo, hi)
        if animate:
            self.cam.start_animation(self.cam.rot, c, d)
            self._timer.start()
        else:
            self.cam.target, self.cam.distance = c, d
            self.pick_dirty = True
            self.update()

    def look_at_frame(self, frame: K.Frame):
        """Look straight at a sketch plane (Fusion's 'Look At')."""
        q = matrix_quat(np.column_stack([frame.xdir, frame.ydir, frame.normal]))
        self.cam.start_animation(q, self.cam.target if self.doc and self.vstate.bodies else frame.origin,
                                 self.cam.distance)
        self._timer.start()

    def scene_bounds(self):
        los, his = [], []
        if self.doc:
            for b in self.vstate.bodies.values():
                if not self.doc.body_visible(b.id):
                    continue
                lo, hi = K.bbox(b.shape)
                los.append(lo)
                his.append(hi)
            for fid, sk in self.vstate.sketches.items():
                if not self._sketch_visible(fid):
                    continue
                pts = [sk.frame.to_world(sk.sketch.xy(p.id)) for p in sk.sketch.points()]
                if len(pts) > 1:
                    los.append(np.min(pts, 0))
                    his.append(np.max(pts, 0))
        if not los:
            return np.array([-50.0, -50, -50]), np.array([50.0, 50, 50])
        return np.min(los, 0), np.max(his, 0)

    # ------------------------------------------------------------------ scene building
    def _sketch_visible(self, fid):
        if self.sketch_ctx and self.sketch_ctx[0] == fid:
            return True
        return self.doc.body_props.get(fid, {}).get("visible", True)

    def _rebuild_scene(self):
        doc = self.doc
        self.reg.clear()
        self.body_ids.clear()
        self._sketch_elem.clear()
        # ---- bodies
        live = set()
        if doc is not None:
            for b in self.vstate.bodies.values():
                live.add(b.id)
                cached = self.gpu.get(b.id)
                if cached is None or cached[0] != b.token:
                    if cached:
                        cached[1].delete()
                    t0 = time.perf_counter()
                    mesh = K.tessellate(b.shape)
                    self.gpu[b.id] = (b.token, G.BodyGPU(mesh))
                    self.status.emit(f"Tessellated {doc.body_name(b.id)} in {(time.perf_counter() - t0) * 1000:.0f} ms")
                g = self.gpu[b.id][1]
                fb = self.reg.alloc(g.mesh.face_count, "face", b.id)
                eb = self.reg.alloc(len(g.mesh.edge_lines), "edge", b.id) - 1  # line ids are 1-based
                vb = self.reg.alloc(len(g.mesh.vertex_points), "vertex", b.id) - 1
                self.body_ids[b.id] = (fb, eb, vb)
        for bid in list(self.gpu):
            if bid not in live:
                self.gpu.pop(bid)[1].delete()
        # ---- previews
        for g in self._preview_gpu:
            g[0].delete()
        self._preview_gpu = []
        for shape, rgb, alpha in self.preview_shapes:
            try:
                self._preview_gpu.append((G.BodyGPU(K.tessellate(shape)), rgb, alpha))
            except Exception:
                pass
        # ---- sketches, planes
        self._build_sketches()
        self._build_planes()
        lo, hi = self.scene_bounds()
        self._scene_radius = max(float(np.linalg.norm(hi - lo)), 100.0)
        self.scene_dirty = False
        self.pick_dirty = True

    def _sketch_colors(self, sk, e, active):
        sel = any(p.kind in ("curve", "spoint") and p.index == e.id and p.key == sk for p in self.selection)
        if sel:
            return THEME.sk_selected
        return None

    def _build_sketches(self):
        for b in (self.sketch_batch, self.sketch_pts, self.sketch_construction, self.profile_batch):
            b.clear()
        doc = self.doc
        if doc is None:
            return
        sketches = dict(self.vstate.sketches)
        if self.sketch_ctx is not None:
            fid, sketch, frame = self.sketch_ctx
            from ..core.document import SketchOut
            sketches[fid] = SketchOut(frame, sketch)
        for fid, so in sketches.items():
            active = self.sketch_ctx is not None and self.sketch_ctx[0] == fid
            if not self._sketch_visible(fid):
                continue
            sk, fr = so.sketch, so.frame
            curves = sk.curves()
            cbase = self.reg.alloc(max((e.id for e in sk.entities.values()), default=0) + 1, "curve", fid)
            for e in curves:
                pls = sk.polylines(e, seg_len=max(self.cam.pixel_size_at(fr.origin) * 3, 1e-3))
                selected = any(p.kind == "curve" and p.key == fid and p.index == e.id for p in self.selection)
                if selected:
                    col = THEME.sk_selected
                elif e.construction:
                    col = THEME.sk_construction
                elif active:
                    col = THEME.sk_constrained if e.id in sk.constrained else THEME.sk_free
                else:
                    col = THEME.sk_inactive
                target = self.sketch_construction if e.construction else self.sketch_batch
                for pl in pls:
                    target.add_polyline(fr.to_world(pl), (*col, 1.0), cbase + e.id)
            if active or self.show_points:
                pbase = self.reg.alloc(max((e.id for e in sk.entities.values()), default=0) + 1, "spoint", fid)
                for p in sk.points():
                    if not active and (p.owner is not None or p.id == 0):
                        continue
                    selected = any(q.kind == "spoint" and q.key == fid and q.index == p.id for q in self.selection)
                    col = THEME.sk_selected if selected else (THEME.sk_constrained if p.id in sk.constrained
                                                              else THEME.sk_free)
                    if p.id == 0:
                        col = THEME.sk_origin
                    self.sketch_pts.add_points(fr.to_world(sk.xy(p.id)), (*col, 1.0), pbase + p.id)
            # Profiles (closed regions)
            show_prof = (active and not self.hide_profiles) or fid in self.show_profiles_for
            if show_prof:
                try:
                    profs = so.profiles if not active else K.build_profiles(sk, fr)
                except Exception:
                    profs = []
                prbase = self.reg.alloc(len(profs), "profile", fid)
                self._profiles_cache = getattr(self, "_profiles_cache", {})
                self._profiles_cache[fid] = profs
                for i, face in enumerate(profs):
                    try:
                        m = K.tessellate(face)
                    except Exception:
                        continue
                    tri = m.positions[m.indices.ravel()]
                    selected = any(p.kind == "profile" and p.key == fid and p.index == i for p in self.selection)
                    col = (*THEME.profile_sel, 0.55) if selected else (*THEME.profile, 0.28)
                    self.profile_batch.add_triangles(tri, col, prbase + i)

    def _build_planes(self):
        self.plane_batch.clear()
        self.plane_lines.clear()
        doc = self.doc
        planes = []
        size = 60.0
        if doc is not None and (self.show_origin or (self.filter and "plane" in self.filter)):
            for name, fr in K.ORIGIN_FRAMES.items():
                planes.append(("origin_plane", name, fr, THEME.plane_colors[name]))
        if doc is not None:
            for fid, fr in self.vstate.planes.items():
                if doc.body_props.get(fid, {}).get("visible", True):
                    planes.append(("plane", fid, fr, THEME.construct))
        if not planes:
            return
        base = self.reg.alloc(len(planes), "plane", "*")
        self._plane_list = planes
        for i, (kind, key, fr, col) in enumerate(planes):
            uv = np.array([[0, 0], [size, 0], [size, size], [0, size]], float)
            if kind == "plane":
                uv -= size / 2
            pts = fr.to_world(uv)
            sel = any(p.kind == "plane" and p.key == key for p in self.selection)
            alpha = 0.35 if sel else 0.12
            self.plane_batch.add_triangles(pts[[0, 1, 2, 0, 2, 3]], (*col, alpha), base + i)
            self.plane_lines.add_polyline(pts, (*col, 0.9), 0, closed=True)

    def _build_grid(self, frame: K.Frame):
        # Adaptive spacing: ~ 40 px between minor lines
        px = self.cam.pixel_size_at(self.cam.target)
        raw = px * 30
        step = 10 ** math.floor(math.log10(max(raw, 1e-6)))
        for m in (1, 2, 5, 10):
            if step * m >= raw:
                step *= m
                break
        extent = step * 60
        c = frame.to_local(self.cam.target)
        cu, cv = (np.round(c / (step * 5)) * step * 5)
        key = (round(step, 9), round(cu, 6), round(cv, 6), tuple(np.round(frame.normal, 6)),
               tuple(np.round(frame.origin, 6)))
        if key == self._grid_key:
            return
        self._grid_key = key
        self.grid.clear()
        self.grid_minor.clear()
        n = 60
        for i in range(-n, n + 1):
            for pts in (np.array([[cu + i * step, cv - extent], [cu + i * step, cv + extent]]),
                        np.array([[cu - extent, cv + i * step], [cu + extent, cv + i * step]])):
                major = abs(round((pts[0][0] if pts[0][0] == pts[1][0] else pts[0][1]) / step)) % 5 == 0
                tgt = self.grid if major else self.grid_minor
                a = 0.38 if major else 0.16
                tgt.add_polyline(frame.to_world(pts), (*THEME.grid, a))
        self.grid_step = step

    # ------------------------------------------------------------------ painting
    def paintGL(self):
        t0 = time.perf_counter()
        if self.r is None:
            return
        if self.scene_dirty:
            self._rebuild_scene()
        dpr = self._dpr()
        W, H = int(self.width() * dpr), int(self.height() * dpr)
        self.cam.width, self.cam.height = self.width(), self.height()
        self._paint_scene(W, H, dpr)
        # overlay
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._draw_overlay(p)
        p.end()
        self.fps_ms = (time.perf_counter() - t0) * 1000

    def render_image(self, width: int, height: int, background="gradient", samples=4, shadows=True):
        """Render the model (no grid, origin, sketches, selection or UI) into an image of any size."""
        from PySide6.QtGui import QImage
        from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        self.makeCurrent()
        saved = (self.selection, self.hover, self.show_grid, self.show_origin, self.cam.width, self.cam.height,
                 THEME.bg_top, THEME.bg_bottom)
        try:
            if self.scene_dirty:
                self._rebuild_scene()
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
            fmt.setSamples(samples)
            fbo = QOpenGLFramebufferObject(int(width), int(height), fmt)
            fbo.bind()
            self.selection, self.hover, self.show_grid, self.show_origin = [], None, False, False
            if background == "white":
                THEME.bg_top = THEME.bg_bottom = (1.0, 1.0, 1.0)
            self.cam.width, self.cam.height = self.width(), self.width() * height / width
            self._rendering_clean = True
            self._render_shadows = shadows
            self._paint_scene(int(width), int(height), width / max(self.width(), 1))
            img = fbo.toImage()
            fbo.release()
            return img
        finally:
            self._rendering_clean = False
            (self.selection, self.hover, self.show_grid, self.show_origin, self.cam.width, self.cam.height,
             THEME.bg_top, THEME.bg_bottom) = saved
            self.doneCurrent()
            self.update()

    def _paint_scene(self, W, H, dpr):
        r = self.r
        r.clip = self._clip_vec()
        r.begin(W, H, THEME.bg_top, THEME.bg_bottom)
        mvp = self.cam.mvp(self._scene_radius)
        view = self.cam.view_matrix()
        vp = (W, H)

        # grid
        frame = self.sketch_ctx[2] if self.sketch_ctx else K.ORIGIN_FRAMES["XY"]
        if self.show_grid:
            self._build_grid(frame)
            GL.glDepthMask(GL.GL_FALSE)
            r.draw_lines(self.grid_minor, mvp, vp, 1.0 * dpr)
            r.draw_lines(self.grid, mvp, vp, 1.0 * dpr)
            GL.glDepthMask(GL.GL_TRUE)

        # bodies
        doc = self.doc
        sel_faces, sel_edges, sel_verts = {}, {}, {}
        for p in self.selection:
            d = {"face": sel_faces, "edge": sel_edges, "vertex": sel_verts}.get(p.kind)
            if d is not None:
                d.setdefault(p.key, []).append(p.index)
        if doc is not None:
            transparent = []
            for b in self.vstate.bodies.values():
                if not doc.body_visible(b.id) or b.id in self.hidden_bodies or b.id not in self.gpu:
                    continue
                g = self.gpu[b.id][1]
                col = doc.body_color(b.id)
                body_sel = any(p.kind == "body" and p.key == b.id for p in self.selection)
                hl = self.hover.index if (self.hover and self.hover.kind == "face" and self.hover.key == b.id) else -1
                alpha = doc.body_props.get(b.id, {}).get("opacity", 1.0)
                if self.sketch_ctx is not None:
                    alpha = min(alpha, 0.45)
                if self.style != "wireframe":
                    if alpha < 1.0:
                        transparent.append((g, col, alpha, hl))
                    else:
                        r.draw_body(g, mvp, view, col, 1.0, hl, THEME.hover)
                if body_sel:
                    r.draw_faces_flat(g, mvp, view, list(g.face_ranges), THEME.select, 0.35)
                elif b.id in self.highlight_bodies:
                    r.draw_faces_flat(g, mvp, view, list(g.face_ranges), THEME.hover, 0.25)
                if b.id in sel_faces:
                    r.draw_faces_flat(g, mvp, view, sel_faces[b.id], THEME.select, 0.55)
                if self.style in ("shaded_edges", "wireframe"):
                    r.draw_edges(g, mvp, vp, (*THEME.edge, 0.9), 1.2 * dpr)
                if self.hover and self.hover.kind == "edge" and self.hover.key == b.id:
                    r.draw_edges(g, mvp, vp, (*THEME.hover, 1.0), 3.0 * dpr, [self.hover.index])
                if b.id in sel_edges:
                    r.draw_edges(g, mvp, vp, (*THEME.select, 1.0), 3.0 * dpr, sel_edges[b.id])
                if self.hover and self.hover.kind == "vertex" and self.hover.key == b.id:
                    r.draw_vertices(g, mvp, (*THEME.hover, 1), 9 * dpr, [self.hover.index])
                if b.id in sel_verts:
                    r.draw_vertices(g, mvp, (*THEME.select, 1), 9 * dpr, sel_verts[b.id])
            for g, col, alpha, hl in transparent:
                r.draw_body(g, mvp, view, col, alpha, hl, THEME.hover)
                if self.style in ("shaded_edges", "wireframe"):
                    r.draw_edges(g, mvp, vp, (*THEME.edge, 0.35), 1.0 * dpr)
            for g, rgb, alpha in self._preview_gpu:
                r.draw_body(g, mvp, view, rgb, alpha)
                r.draw_edges(g, mvp, vp, (*rgb, 0.9), 1.2 * dpr)

        # construction planes
        if getattr(self, "_rendering_clean", False):
            if getattr(self, "_render_shadows", False) and doc is not None:
                gpus = [self.gpu[b.id][1] for b in self.vstate.bodies.values()
                        if doc.body_visible(b.id) and b.id not in self.hidden_bodies and b.id in self.gpu]
                shapes = [b.shape for b in self.vstate.bodies.values() if doc.body_visible(b.id) and b.id in self.gpu]
                if gpus and shapes:
                    lo, hi = K.bbox(K.compound(shapes))
                    c = (lo + hi) / 2
                    rad = max(float(np.linalg.norm(hi - lo)) / 2, 1.0)
                    GL.glDisable(GL.GL_CLIP_DISTANCE0)
                    r.draw_ground_shadow(gpus, mvp, c, rad, float(lo[2]), (0.6, 0.5, 0.9))
            GL.glDisable(GL.GL_CLIP_DISTANCE0)
            return
        r.draw_tris(self.plane_batch, mvp, self._hover_local("plane"))
        r.draw_lines(self.plane_lines, mvp, vp, 1.2 * dpr)
        if self.show_origin or self.sketch_ctx is not None:
            self._draw_axes(mvp, vp, dpr)

        # sketches
        in_sketch = self.sketch_ctx is not None
        r.draw_tris(self.profile_batch, mvp, self._hover_local("profile"))
        r.draw_lines(self.sketch_batch, mvp, vp, 1.8 * dpr, depth=not in_sketch)
        r.draw_lines(self.sketch_construction, mvp, vp, 1.4 * dpr, dash=8 * dpr, depth=not in_sketch)
        hc = self._hover_curve()
        if hc is not None:
            b = G.Batch()
            for pl in hc:
                b.add_polyline(pl, (*THEME.hover, 1.0))
            r.draw_lines(b, mvp, vp, 3.2 * dpr, depth=False)
            b.gpu and b.gpu.delete()
        r.draw_points(self.sketch_pts, mvp, 7 * dpr, depth=not in_sketch)
        if self.hover and self.hover.kind in ("spoint", "origin"):
            b = G.Batch()
            b.add_points(self.hover.point, (*THEME.hover, 1))
            r.draw_points(b, mvp, 10 * dpr, depth=False)
            b.gpu and b.gpu.delete()
        # tool rubber-band
        if self.tool_lines.pos:
            r.draw_lines(self.tool_lines, mvp, vp, 1.8 * dpr, depth=False)
        if self.tool_points.pos:
            r.draw_points(self.tool_points, mvp, 8 * dpr, round_=True, depth=False)
        GL.glDisable(GL.GL_CLIP_DISTANCE0)

    def _clip_vec(self):
        if not self.section:
            return np.array([0, 0, 0, 1.0])
        o, n = self.section
        n = np.asarray(n, float)
        return np.array([*(-n), float(np.dot(n, o))])

    def _hover_local(self, kind):
        """Pick id of the hovered triangle-batch element (shader highlight)."""
        if self.hover is None or self.hover.kind != kind:
            return -1
        return getattr(self, "_hover_pid", -1)

    def _hover_curve(self):
        h = self.hover
        if h is None or h.kind != "curve":
            return None
        so = self._sketch_out(h.key)
        if so is None or h.index not in so.sketch.entities:
            return None
        pls = so.sketch.polylines(so.sketch.entities[h.index])
        return [so.frame.to_world(pl) for pl in pls]

    def _sketch_out(self, fid):
        if self.sketch_ctx and self.sketch_ctx[0] == fid:
            from ..core.document import SketchOut
            return SketchOut(self.sketch_ctx[2], self.sketch_ctx[1])
        return self.vstate.sketches.get(fid) if self.doc else None

    def _draw_axes(self, mvp, vp, dpr):
        b = G.Batch()
        L = self.cam.pixel_size_at(self.cam.target) * 80
        if self.sketch_ctx is None:
            L = max(L, 60)
        for d, c in (([1, 0, 0], THEME.axis_x), ([0, 1, 0], THEME.axis_y), ([0, 0, 1], THEME.axis_z)):
            b.add_polyline(np.array([[0, 0, 0], np.array(d) * L]), (*c, 0.9))
        self.r.draw_lines(b, mvp, vp, 1.5 * dpr)
        b.gpu and b.gpu.delete()

    # ------------------------------------------------------------------ overlay (QPainter)
    def _draw_annotations(self, p: QPainter):
        """Cosmetic thread labels etc. (not part of the B-rep)."""
        if self.display_state is None and self.doc is None:
            return
        f = QFont(self.font())
        f.setPointSizeF(8)
        f.setItalic(True)
        p.setFont(f)
        for a in self.vstate.annotations:
            try:
                sc = self.screen_of(np.asarray(a["point"], float))
            except Exception:
                continue
            fm = QFontMetrics(f)
            w = fm.horizontalAdvance(a["text"]) + 10
            r = QRectF(sc[0] - w / 2, sc[1] - 9, w, 18)
            p.setPen(QPen(QColor(20, 120, 160), 1))
            p.setBrush(QColor(230, 246, 252, 225) if THEME.light else QColor(30, 60, 72, 225))
            p.drawRoundedRect(r, 9, 9)
            p.setPen(QColor(15, 90, 125) if THEME.light else QColor(150, 220, 245))
            p.drawText(r, Qt.AlignCenter, a["text"])

    def ray_faces(self, x, y, limit=12):
        """All faces pierced by the ray under the cursor, nearest first:
        [(Pick, depth behind the first hit in mm)].  Lets the user pick faces
        hidden behind others (Clarify Selection)."""
        o, d = self.cam.ray(x, y)
        o = np.asarray(o, float)
        d = np.asarray(d, float)
        hits = []
        for b in self.vstate.bodies.values():
            if self.doc is None or not self.doc.body_visible(b.id) or b.id in self.hidden_bodies:
                continue
            g = self.gpu.get(b.id)
            if g is None or len(g[1].mesh.indices) == 0:
                continue
            m = g[1].mesh
            P = m.positions.astype(np.float64)
            T = m.indices.astype(np.int64)
            v0, v1, v2 = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
            e1, e2 = v1 - v0, v2 - v0
            h = np.cross(d, e2)
            a = np.einsum("ij,ij->i", e1, h)
            ok = np.abs(a) > 1e-12
            f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
            sv = o - v0
            u = f * np.einsum("ij,ij->i", sv, h)
            q = np.cross(sv, e1)
            vv = f * (q @ d)
            t = f * np.einsum("ij,ij->i", e2, q)
            m_ok = ok & (u >= 0) & (vv >= 0) & (u + vv <= 1) & (t > 0)
            best = {}
            for ti in np.flatnonzero(m_ok):
                fi = int(m.face_of_tri[ti])
                if fi not in best or t[ti] < best[fi]:
                    best[fi] = float(t[ti])
            hits += [(t_, b.id, fi) for fi, t_ in best.items()]
        hits.sort()
        if not hits:
            return []
        t0 = hits[0][0]
        return [(Pick("face", bid, fi), t_ - t0) for t_, bid, fi in hits[:limit]]

    def _draw_overlay(self, p: QPainter):
        self._draw_annotations(p)
        self._draw_manipulators(p)
        if self._box is not None:
            x0, y0, x1, y1 = self._box
            crossing = x1 < x0
            p.setPen(QPen(QColor(10, 100, 214), 1, Qt.DashLine if crossing else Qt.SolidLine))
            p.setBrush(QColor(10, 160, 60, 40) if crossing else QColor(10, 100, 214, 40))
            p.drawRect(QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized())
        self._draw_view_cube(p)
        self._draw_triad(p)
        if self.tool is not None and hasattr(self.tool, "paint"):
            self.tool.paint(p, self)
        if self.sketch_ctx is not None:
            self._paint_sketch_annotations(p)
        for pt, text, col in self.labels:
            s = self.cam.project(pt)[0]
            self._label(p, s[0], s[1], text, col)
        if self.section:
            p.setPen(_qc(THEME.text))
            p.drawText(12, self.height() - 40, "Section Analysis active")

    def _label(self, p, x, y, text, col=None, bg=True):
        f = QFont(self.font())
        f.setPointSizeF(9)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(text) + 10
        h = fm.height() + 4
        rect = QRectF(x - w / 2, y - h / 2, w, h)
        if bg:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 225) if THEME.light else QColor(40, 42, 48, 225))
            p.drawRoundedRect(rect, 3, 3)
        p.setPen(_qc(col or THEME.dim_text))
        p.drawText(rect, Qt.AlignCenter, text)
        return rect

    def _paint_sketch_annotations(self, p: QPainter):
        """Dimensions and constraint glyphs for the active sketch."""
        from ..core.expressions import format_angle, format_length
        fid, sk, fr = self.sketch_ctx
        W = lambda uv: self.cam.project(fr.to_world(uv))[0][:2]  # noqa: E731
        self._dim_rects = {}
        pen = QPen(_qc(THEME.dim_line), 1.0)
        for c in sk.constraints.values():
            if not c.param or not self.show_dimensions:
                continue
            try:
                val = self.doc.param_value(c.param)
                expr = self.doc.params.params[c.param].expr
            except Exception:
                continue
            txt = format_angle(val) if c.kind == "angle" else format_length(val)
            if not _is_plain_number(expr, val, c.kind):
                txt = f"fx: {txt}"  # driven by an expression / parameter
            sel = any(q.kind == "constraint" and q.index == c.id for q in self.selection)
            col = THEME.select if sel else THEME.dim_text
            pos = self._dim_anchor(sk, c)
            if pos is None:
                continue
            (a, b), lab = pos
            sa, sb, sl = W(a), W(b), W(lab)
            p.setPen(QPen(_qc(col), 1.0))
            if c.kind in ("radius", "diameter"):
                p.drawLine(QPointF(*sa), QPointF(*sl))
            elif c.kind != "angle":
                # extension lines + dimension line through the label
                off = sl - (sa + sb) / 2
                da, db = sa + off, sb + off
                p.setPen(QPen(_qc(THEME.dim_line), 0.8, Qt.DashLine))
                p.drawLine(QPointF(*sa), QPointF(*da))
                p.drawLine(QPointF(*sb), QPointF(*db))
                p.setPen(QPen(_qc(col), 1.0))
                p.drawLine(QPointF(*da), QPointF(*db))
                for tip, other in ((da, db), (db, da)):
                    self._arrow(p, tip, other, col)
            else:
                p.drawLine(QPointF(*sa), QPointF(*sl))
            prefix = {"radius": "R", "diameter": "⌀"}.get(c.kind, "")
            rect = self._label(p, sl[0], sl[1], prefix + txt, col)
            self._dim_rects[c.id] = rect
        # constraint glyphs
        glyph = {"horizontal": "H", "vertical": "V", "parallel": "∥", "perpendicular": "⊥", "tangent": "T",
                 "equal": "=", "coincident": "", "concentric": "◎", "midpoint": "△", "fix": "🔒",
                 "collinear": "≡", "symmetric": "[]"}
        f = QFont(self.font())
        f.setPointSizeF(8)
        p.setFont(f)
        self._glyph_rects = {}
        counts = {}
        for c in sk.constraints.values():
            g = glyph.get(c.kind)
            if not g or not self.show_constraints:
                continue
            for ref in c.refs[:2]:
                e = sk.entities.get(ref)
                if e is None:
                    continue
                if e.kind == "point":
                    anchor = np.array(sk.xy(e.id))
                elif e.kind == "line":
                    anchor = (np.array(sk.xy(e.pts[0])) + np.array(sk.xy(e.pts[1]))) / 2
                else:
                    anchor = np.array(sk.xy(e.pts[0])) + np.array([e.r * 0.7, e.r * 0.7])
                s = W(anchor)
                k = counts.get(ref, 0)
                counts[ref] = k + 1
                rect = QRectF(s[0] + 8 + k * 15, s[1] + 6, 14, 14)
                sel = any(q.kind == "constraint" and q.index == c.id for q in self.selection)
                p.setPen(Qt.NoPen)
                p.setBrush(_qc(THEME.select) if sel else QColor(255, 255, 255, 230) if THEME.light else QColor(50, 52, 58, 230))
                p.drawRoundedRect(rect, 2, 2)
                p.setPen(_qc(THEME.glyph))
                p.drawText(rect, Qt.AlignCenter, g)
                self._glyph_rects.setdefault(c.id, []).append(rect)
        # DOF / status
        p.setPen(_qc(THEME.text))
        f.setPointSizeF(9)
        p.setFont(f)
        msg = "Fully constrained" if sk.dof == 0 else f"{sk.dof} degrees of freedom"
        p.drawText(12, self.height() - 14, f"SKETCH  ·  {msg}")

    def _arrow(self, p, tip, other, col):
        d = other - tip
        n = np.linalg.norm(d)
        if n < 1e-6:
            return
        d = d / n * 7
        perp = np.array([-d[1], d[0]]) * 0.45
        poly = QPolygonF([QPointF(*tip), QPointF(*(tip + d + perp)), QPointF(*(tip + d - perp))])
        p.setBrush(_qc(col))
        p.setPen(Qt.NoPen)
        p.drawPolygon(poly)

    def _dim_anchor(self, sk, c):
        """Returns ((a, b), label_pos) in sketch coordinates."""
        E = sk.entities
        off = np.array(c.data.get("offset", [0.0, 0.0]))
        try:
            if c.kind in ("radius", "diameter"):
                e = E[c.refs[0]]
                ctr = np.array(sk.xy(e.pts[0]))
                ang = c.data.get("ang", 0.785)
                a = ctr + e.r * np.array([math.cos(ang), math.sin(ang)])
                return (a, ctr), a + (a - ctr) / max(e.r, 1e-9) * 6 + off
            if c.kind == "angle":
                l1, l2 = E[c.refs[0]], E[c.refs[1]]
                p1 = (np.array(sk.xy(l1.pts[0])) + np.array(sk.xy(l1.pts[1]))) / 2
                p2 = (np.array(sk.xy(l2.pts[0])) + np.array(sk.xy(l2.pts[1]))) / 2
                m = (p1 + p2) / 2
                return (m, m), m + off
            refs = c.refs
            if len(refs) == 1:
                e = E[refs[0]]
                a, b = np.array(sk.xy(e.pts[0])), np.array(sk.xy(e.pts[1]))
            else:
                pts = []
                for r in refs:
                    e = E[r]
                    if e.kind == "point":
                        pts.append(np.array(sk.xy(r)))
                    elif e.kind == "line":
                        pts.append((np.array(sk.xy(e.pts[0])) + np.array(sk.xy(e.pts[1]))) / 2)
                    else:
                        pts.append(np.array(sk.xy(e.pts[0])))
                a, b = pts
                if E[refs[0]].kind == "point" and E[refs[1]].kind == "line" or \
                        E[refs[0]].kind == "line" and E[refs[1]].kind == "point":
                    pid, lid = (refs if E[refs[0]].kind == "point" else refs[::-1])
                    la, lb = (np.array(sk.xy(i)) for i in E[lid].pts)
                    pp = np.array(sk.xy(pid))
                    d = lb - la
                    t = np.dot(pp - la, d) / max(np.dot(d, d), 1e-12)
                    a, b = pp, la + d * t
            if c.kind == "hdistance":
                b = np.array([b[0], a[1]])
            elif c.kind == "vdistance":
                b = np.array([a[0], b[1]])
            d = b - a
            n = np.linalg.norm(d)
            nrm = np.array([-d[1], d[0]]) / n if n > 1e-9 else np.array([0, 1.0])
            px = self.cam.pixel_size_at(self.sketch_ctx[2].origin)
            default = nrm * 22 * px
            lab = (a + b) / 2 + (off if c.data.get("offset") else default)
            return (a, b), lab
        except (KeyError, IndexError):
            return None

    def dimension_at(self, x, y):
        for cid, rect in getattr(self, "_dim_rects", {}).items():
            if rect.contains(QPointF(x, y)):
                return cid
        return None

    def glyph_at(self, x, y):
        for cid, rects in getattr(self, "_glyph_rects", {}).items():
            if any(r.contains(QPointF(x, y)) for r in rects):
                return cid
        return None

    # ---- view cube
    CUBE = 64

    def _cube_center(self):
        return np.array([self.width() - 95.0, 100.0])

    def _cube_faces(self):
        R = self.cam.rotation().T  # world -> camera
        s = self.CUBE / 2
        c = self._cube_center()
        faces = {"Top": ([0, 0, 1], [0, 1, 0]), "Bottom": ([0, 0, -1], [0, -1, 0]), "Front": ([0, -1, 0], [0, 0, 1]),
                 "Back": ([0, 1, 0], [0, 0, 1]), "Right": ([1, 0, 0], [0, 0, 1]), "Left": ([-1, 0, 0], [0, 0, 1])}
        out = []
        for name, (n, up) in faces.items():
            n, up = np.array(n, float), np.array(up, float)
            rt = np.cross(up, n)
            corners = [n * s + (rt * a + up * b) * s for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            cam = [R @ v for v in corners]
            depth = (R @ n)[2]
            pts = [QPointF(c[0] + v[0], c[1] - v[1]) for v in cam]
            out.append((depth, name, QPolygonF(pts), R @ (n * s)))
        out.sort(key=lambda t: t[0])
        return out

    def _draw_view_cube(self, p: QPainter):
        f = QFont(self.font())
        f.setPointSizeF(6.5)
        f.setBold(True)
        p.setFont(f)
        for depth, name, poly, ctr in self._cube_faces():
            if depth <= 0.02:
                continue
            hov = self._cube_hover == name
            base = QColor(120, 170, 235) if hov else (QColor(238, 241, 246) if THEME.light else QColor(80, 84, 92))
            shade = 0.78 + 0.22 * depth
            col = QColor.fromRgbF(base.redF() * shade, base.greenF() * shade, base.blueF() * shade, 0.95)
            p.setBrush(col)
            p.setPen(QPen(QColor(120, 125, 135), 1))
            p.drawPolygon(poly)
            if depth > 0.25:
                c = self._cube_center()
                p.setPen(QColor(60, 64, 72) if THEME.light else QColor(230, 230, 235))
                p.drawText(QRectF(c[0] + ctr[0] - 30, c[1] - ctr[1] - 8, 60, 16), Qt.AlignCenter, name.upper())
        # home button
        c = self._cube_center()
        r = QRectF(c[0] - 78, c[1] - 78, 16, 16)
        self._home_rect = r
        p.setPen(QPen(_qc(THEME.text), 1.4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(r.left() + 2, r.center().y())
        path.lineTo(r.center().x(), r.top() + 2)
        path.lineTo(r.right() - 2, r.center().y())
        p.drawPath(path)
        p.drawRect(QRectF(r.left() + 4, r.center().y(), r.width() - 8, r.height() / 2 - 2))

    CUBE_FACES = {"Top": ([0, 0, 1], [0, 1, 0]), "Bottom": ([0, 0, -1], [0, -1, 0]), "Front": ([0, -1, 0], [0, 0, 1]),
                  "Back": ([0, 1, 0], [0, 0, 1]), "Right": ([1, 0, 0], [0, 0, 1]), "Left": ([-1, 0, 0], [0, 0, 1])}

    def _cube_pick(self, x, y):
        """Return (label, view_dir, up) for the ViewCube region under (x, y).

        Clicking near a face's border picks the adjacent edge view, near a
        corner the corner (isometric) view -- 26 views like Fusion's cube.
        """
        pt = QPointF(x, y)
        if getattr(self, "_home_rect", None) is not None and self._home_rect.contains(pt):
            return ("Home",) + tuple(np.array(v, float) for v in STANDARD_VIEWS["Home"])
        for depth, name, poly, _ in reversed(self._cube_faces()):
            if depth <= 0.02 or not poly.containsPoint(pt, Qt.OddEvenFill):
                continue
            c0, c1, c3 = poly[0], poly[1], poly[3]
            a = np.array([[c1.x() - c0.x(), c3.x() - c0.x()], [c1.y() - c0.y(), c3.y() - c0.y()]])
            try:
                uv = np.linalg.solve(a, [x - c0.x(), y - c0.y()]) * 2 - 1
            except np.linalg.LinAlgError:
                uv = np.zeros(2)
            n, up = (np.array(v, float) for v in self.CUBE_FACES[name])
            rt = np.cross(up, n)
            d = n.copy()
            if abs(uv[0]) > 0.55:
                d += rt * np.sign(uv[0])
            if abs(uv[1]) > 0.55:
                d += up * np.sign(uv[1])
            d /= np.linalg.norm(d)
            label = name if np.allclose(d, n) else f"{name}*"
            if abs(d[2]) < 0.99:
                view_up = np.array([0, 0, 1.0])
            else:
                view_up = np.array([0, 1.0, 0]) if d[2] > 0 else np.array([0, -1.0, 0])
            return label, -d, view_up
        return None

    def _draw_triad(self, p: QPainter):
        R = self.cam.rotation().T
        o = np.array([42.0, self.height() - 42.0])
        for d, c, lab in (([1, 0, 0], THEME.axis_x, "X"), ([0, 1, 0], THEME.axis_y, "Y"), ([0, 0, 1], THEME.axis_z, "Z")):
            v = R @ np.array(d, float) * 26
            e = o + np.array([v[0], -v[1]])
            p.setPen(QPen(_qc(c), 2.2))
            p.drawLine(QPointF(*o), QPointF(*e))
            p.drawText(QPointF(e[0] + 2, e[1] + 4), lab)

    # ------------------------------------------------------------------ picking
    def _render_pick(self):
        if not self.pick_dirty or self.r is None:
            return
        self.makeCurrent()
        if self.scene_dirty:
            self._rebuild_scene()
        dpr = self._dpr()
        W, H = int(self.width() * dpr), int(self.height() * dpr)
        r = self.r
        r.clip = self._clip_vec()
        r.begin_pick(W, H)
        GL.glEnable(GL.GL_CLIP_DISTANCE0)
        mvp = self.cam.mvp(self._scene_radius)
        view = self.cam.view_matrix()
        vp = (W, H)
        doc = self.doc
        in_sketch = self.sketch_ctx is not None
        if doc is not None:
            want_e = self.accepts("edge") or in_sketch
            want_v = self.accepts("vertex") or in_sketch
            for bid, (fb, eb, vb) in self.body_ids.items():
                if not doc.body_visible(bid) or bid in self.hidden_bodies or bid not in self.gpu:
                    continue
                r.pick_body(self.gpu[bid][1], mvp, view, fb, eb, vb, vp, edges=want_e, verts=want_v)
        if self.accepts("plane"):
            r.pick_tris(self.plane_batch, mvp, 0)
        if self.accepts("profile"):
            r.pick_tris(self.profile_batch, mvp, 0)
        r.pick_lines(self.sketch_batch, mvp, vp, 0, 7.0 * dpr, depth=not in_sketch)
        r.pick_lines(self.sketch_construction, mvp, vp, 0, 7.0 * dpr, depth=not in_sketch)
        r.pick_points(self.sketch_pts, mvp, 0, 13 * dpr, depth=not in_sketch)
        GL.glDisable(GL.GL_CLIP_DISTANCE0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        self.pick_dirty = False

    def pick_at(self, x, y, kinds=None) -> Pick | None:
        """Best pickable element near widget pixel (x, y)."""
        if self.r is None:
            return None
        self._render_pick()
        self.makeCurrent()
        dpr = self._dpr()
        X, Y = int(x * dpr), int(y * dpr)
        H = int(self.height() * dpr)
        rad = int(7 * dpr)
        ids, dep, (x0, y0) = self.r.read_pick(X, Y, H, rad)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        if ids is None:
            return None
        best = None
        cy, cx = (H - 1 - Y) - y0, X - x0
        for (iy, ix) in zip(*np.nonzero(ids)):
            pid = int(ids[iy, ix])
            res = self.reg.lookup(pid)
            if res is None:
                continue
            kind, key, local = res
            if kind == "plane":
                key = self._plane_list[local][1]
            if kind == "spoint" and local == 0:
                kind = "origin"
            k = kind
            if kinds is not None and k not in kinds:
                continue
            if kinds is None and not self.accepts(k) and not (self.sketch_ctx and k in ("spoint", "origin", "curve")):
                continue
            dist = math.hypot(iy - cy, ix - cx)
            # faces/profiles/planes must be directly under the cursor
            if k in ("face", "profile", "plane") and dist > 1.5:
                continue
            score = (KIND_PRIORITY.get(k, 9), dist)
            if best is None or score < best[0]:
                best = (score, k, key, local, float(dep[iy, ix]), ix + x0, iy + y0, pid)
        if best is None:
            return None
        _, kind, key, local, d, px, py, pid = best
        self._hover_pid = pid
        wp = self.cam.unproject_depth(px / dpr, (H - 1 - py) / dpr, d, self._scene_radius) if d < 1.0 else np.zeros(3)
        if kind in ("spoint", "origin"):
            so = self._sketch_out(key)
            if so is not None and local in so.sketch.entities:
                wp = so.frame.to_world(so.sketch.xy(local))
        return Pick(kind, key, local, tuple(float(v) for v in wp))

    def depth_point(self, x, y):
        """World point of the geometry under the cursor (or None)."""
        self._render_pick()
        self.makeCurrent()
        dpr = self._dpr()
        H = int(self.height() * dpr)
        ids, dep, _ = self.r.read_pick(int(x * dpr), int(y * dpr), H, 0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        if dep is None or dep.size == 0 or dep[0, 0] >= 1.0:
            return None
        return self.cam.unproject_depth(x, y, float(dep[0, 0]), self._scene_radius)

    def plane_point(self, x, y, frame: K.Frame):
        """Intersect the cursor ray with a plane; returns local (u, v)."""
        o, d = self.cam.ray(x, y)
        den = float(np.dot(d, frame.normal))
        if abs(den) < 1e-9:
            return None
        t = float(np.dot(frame.origin - o, frame.normal)) / den
        return frame.to_local(o + d * t)

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        self._press = (x, y, ev.button(), ev.modifiers())
        self._last = (x, y)
        self._moved = False
        btn, mods = ev.button(), ev.modifiers()
        self._box = None
        self._box_anchor = None
        if btn == Qt.LeftButton:
            cube = self._cube_pick(x, y)
            if cube:
                # click = snap to that view, drag = orbit
                self._cube_press = cube
                self._nav = "orbit"
                self._pivot = self.cam.target.copy()
                return
            m = self._manip_at(x, y)
            if m is not None:
                self._manip_drag = m
                self._nav = None
                return
        if btn == Qt.MiddleButton or btn == Qt.RightButton or (btn == Qt.LeftButton and mods & Qt.AltModifier):
            orbit = (btn == Qt.MiddleButton and mods & Qt.ShiftModifier) or btn == Qt.RightButton or \
                (btn == Qt.LeftButton and mods & Qt.AltModifier)
            self._nav = "orbit" if orbit else "pan"
            self._pivot = self.depth_point(x, y) if orbit else None
            if self._pivot is None and orbit:
                self._pivot = self.cam.target.copy()
            self._pan_ref = self.depth_point(x, y) if not orbit else None
            return
        self._nav = None
        if btn == Qt.LeftButton and self.tool is not None and hasattr(self.tool, "press"):
            if self.tool.press(self, x, y, ev):
                self.update()
                return
        if btn == Qt.LeftButton and getattr(self.tool, "drag", None) is None:
            hit = self.pick_at(x, y)
            if hit is None and not (self.sketch_ctx and (self.glyph_at(x, y) or self.dimension_at(x, y))):
                self._box_anchor = (x, y)

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if self._press is not None and math.hypot(x - self._press[0], y - self._press[1]) > 4:
            self._moved = True
        if self._manip_drag is not None:
            self._drag_manip(x, y, final=False)
            return
        if self._box_anchor is not None and self._moved and (ev.buttons() & Qt.LeftButton):
            self._box = (*self._box_anchor, x, y)
            self.update()
            return
        if self._nav and self._last:
            if self._cube_press is not None and not self._moved:
                return
            dx, dy = x - self._last[0], y - self._last[1]
            if self._nav == "orbit":
                self.cam.orbit(dx, dy, self._pivot)
            else:
                self.cam.pan(dx, dy, self._pan_ref)
            self._last = (x, y)
            self.pick_dirty = True
            self.update()
            return
        self._last = (x, y)
        cube = self._cube_pick(x, y)
        cube_name = cube[0].rstrip("*") if cube else None
        if cube_name != self._cube_hover:
            self._cube_hover = cube_name
            self.update()
        if self.tool is not None and hasattr(self.tool, "move"):
            if self.tool.move(self, x, y, ev):
                self.update()
                return
        if ev.buttons() == Qt.NoButton:
            mh = self._manip_at(x, y)
            if mh is not self._manip_hover:
                self._manip_hover = mh
                self.setCursor(Qt.SizeAllCursor if mh is not None else Qt.ArrowCursor)
                self.update()
            if mh is not None:
                return
            h = self.pick_at(x, y)
            if h != self.hover:
                self.hover = h
                self.hover_changed.emit(h)
                self.update()

    def mouseReleaseEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        press = self._press
        self._press = None
        nav = self._nav
        self._nav = None
        if self._manip_drag is not None:
            self._drag_manip(x, y, final=True)
            self._manip_drag = None
            return
        if self._cube_press is not None:
            cube, self._cube_press = self._cube_press, None
            if not self._moved:
                self.animate_view(cube[1], cube[2], fit=cube[0] == "Home")
            return
        if self._box is not None:
            box, self._box, self._box_anchor = self._box, None, None
            self.box_select(box, ev.modifiers())
            self.update()
            return
        self._box_anchor = None
        if press is None:
            return
        if press[2] == Qt.RightButton and not self._moved:
            if self.tool is not None and hasattr(self.tool, "right_click") and self.tool.right_click(self, x, y):
                self.update()
                return
            self.context_requested.emit(ev.globalPosition().toPoint())
            return
        if nav:
            return
        if press[2] != Qt.LeftButton:
            return
        if self.tool is not None and hasattr(self.tool, "release"):
            if self.tool.release(self, x, y, ev):
                self.update()
                return
        if self._moved:
            return
        self.click_select(x, y, ev.modifiers())

    def click_select(self, x, y, mods=Qt.NoModifier):
        p = self.pick_at(x, y)
        additive = bool(mods & (Qt.ShiftModifier | Qt.ControlModifier)) or self.filter is not None
        if self.sketch_ctx is not None and p is None:
            cid = self.glyph_at(x, y) or self.dimension_at(x, y)
            if cid:
                p = Pick("constraint", self.sketch_ctx[0], cid)
        if p is None:
            if not additive or self.filter is None:
                self.clear_selection()
            return
        if p in self.selection:
            self.selection.remove(p)
        else:
            if not additive:
                self.selection.clear()
            self.selection.append(p)
        if self.sketch_ctx is not None or any(q.kind in ("curve", "spoint", "profile", "plane") for q in [p]):
            self.scene_dirty = True
        self.selection_changed.emit()
        self.update()

    def mouseDoubleClickEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if ev.button() == Qt.MiddleButton:
            self.fit_all()
            return
        if ev.button() == Qt.LeftButton:
            if self.tool is not None and hasattr(self.tool, "double_click") and self.tool.double_click(self, x, y):
                self.update()
                return
            if self.sketch_ctx is not None:
                cid = self.dimension_at(x, y)
                if cid:
                    self.double_clicked.emit(Pick("dimension", self.sketch_ctx[0], cid))
                    return
            self.double_clicked.emit(self.pick_at(x, y))

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        x, y = ev.position().x(), ev.position().y()
        factor = 0.85 ** (delta / 120.0)
        pt = self.depth_point(x, y)
        self.cam.zoom(factor, x, y, point=pt)
        self.pick_dirty = True
        self._grid_key = None
        self.update()

    def keyPressEvent(self, ev):
        if self.tool is not None and hasattr(self.tool, "key") and self.tool.key(self, ev):
            self.update()
            return
        super().keyPressEvent(ev)

    def leaveEvent(self, ev):
        if self.hover is not None:
            self.hover = None
            self.update()

    def event(self, ev):
        # Let tools capture plain keys (typed sketch values) before the
        # window's single-key shortcuts fire.
        if ev.type() == QEvent.ShortcutOverride and self.tool is not None and \
                hasattr(self.tool, "wants_key") and self.tool.wants_key(ev):
            ev.accept()
            return True
        if ev.type() == QEvent.KeyPress and ev.key() in (Qt.Key_Tab, Qt.Key_Backtab) and \
                self.tool is not None and hasattr(self.tool, "wants_key") and self.tool.wants_key(ev):
            self.keyPressEvent(ev)  # Tab cycles typed-value fields instead of moving focus
            return True
        return super().event(ev)

    # ------------------------------------------------------------------ manipulators
    def set_manipulators(self, manips):
        self.manipulators = list(manips)
        self._manip_hover = None
        self.update()

    @staticmethod
    def _manip_handle(m):
        return np.asarray(m.origin, float) + np.asarray(m.direction, float) * m.value

    def _manip_at(self, x, y):
        best = None
        for m in self.manipulators:
            s = self.screen_of(self._manip_handle(m))
            d = math.hypot(s[0] - x, s[1] - y)
            if d < 14 and (best is None or d < best[0]):
                best = (d, m)
        return best[1] if best else None

    def _drag_manip(self, x, y, final):
        m = self._manip_drag
        o, d = np.asarray(m.origin, float), np.asarray(m.direction, float)
        ro, rd = self.cam.ray(x, y)
        w0 = o - ro
        b = float(np.dot(d, rd))
        den = 1.0 - b * b
        if den < 1e-6:
            return  # axis points straight at the viewer
        t = (b * float(np.dot(rd, w0)) - float(np.dot(d, w0))) / den
        # snap to a "nice" increment depending on zoom; Ctrl = free drag
        from PySide6.QtWidgets import QApplication
        if not QApplication.keyboardModifiers() & Qt.ControlModifier:
            px = self.cam.pixel_size_at(o) * 6
            step = 10 ** math.floor(math.log10(max(px, 1e-6)))
            for k in (1, 2, 5, 10):
                if step * k >= px:
                    step *= k
                    break
            t = round(t / step) * step
        if m.min_value is not None:
            t = max(m.min_value, t)
        m.value = t
        m.on_drag(t, final)
        self.update()

    def _draw_manipulators(self, p: QPainter):
        for m in self.manipulators:
            o = np.asarray(m.origin, float)
            h = self._manip_handle(m)
            so, sh = self.screen_of(o), self.screen_of(h)
            sd = self.screen_of(o + np.asarray(m.direction) * self.cam.pixel_size_at(o) * 40) - so
            n = np.linalg.norm(sd)
            if n < 1e-6:
                continue
            u = sd / n
            hot = m is self._manip_hover or m is self._manip_drag
            col = QColor(230, 120, 20) if hot else QColor(10, 100, 214)
            p.setPen(QPen(col, 2))
            p.drawLine(QPointF(*so), QPointF(*sh))
            perp = np.array([-u[1], u[0]])
            if m.kind == "arrow":
                tip = sh + u * 24
                p.setPen(QPen(col, 2))
                p.drawLine(QPointF(*sh), QPointF(*(sh + u * 10)))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*(sh + u * 9 + perp * 7)),
                                         QPointF(*(sh + u * 9 - perp * 7))]))
            p.setPen(QPen(QColor(255, 255, 255), 1.5))
            p.setBrush(col)
            p.drawEllipse(QPointF(*sh), 6, 6)
            if m.label:
                self._label(p, sh[0] + perp[0] * 34, sh[1] + perp[1] * 34, m.label,
                            (0.9, 0.45, 0.05) if hot else None)

    # ------------------------------------------------------------------ box selection
    def box_select(self, box, mods=Qt.NoModifier):
        """Window (drag left->right: fully inside) or crossing (right->left) selection."""
        x0, y0, x1, y1 = box
        crossing = x1 < x0
        lo = np.array([min(x0, x1), min(y0, y1)])
        hi = np.array([max(x0, x1), max(y0, y1)])

        def hit(world_pts):
            world_pts = np.asarray(world_pts, float).reshape(-1, 3)
            if len(world_pts) == 0:
                return False
            s2 = self.cam.project(world_pts, self._scene_radius)[:, :2]
            ins = np.all((s2 >= lo) & (s2 <= hi), axis=1)
            return bool(ins.any()) if crossing else bool(ins.all())

        picks = []
        visible_ids = self._ids_in_rect(lo, hi) if crossing and self.sketch_ctx is None else {}
        if self.sketch_ctx is not None:
            fid, sk, fr = self.sketch_ctx
            for e in sk.curves():
                if hit(fr.to_world(np.vstack(sk.polylines(e, seg_len=self.cam.pixel_size_at(fr.origin) * 4) or
                                             [np.zeros((0, 2))]))):
                    picks.append(Pick("curve", fid, e.id))
            for pt in sk.points():
                if pt.id and pt.owner is None and hit(fr.to_world(np.array([sk.xy(pt.id)]))):
                    picks.append(Pick("spoint", fid, pt.id))
        else:
            want_edges = self.filter is not None and "edge" in self.filter
            if self.filter is not None and not want_edges and "face" not in self.filter:
                return
            for b in self.vstate.bodies.values():
                if not self.doc.body_visible(b.id) or b.id in self.hidden_bodies or b.id not in self.gpu:
                    continue
                mesh = self.gpu[b.id][1].mesh
                seen = visible_ids.get(b.id, {})
                if want_edges:
                    for i, pl in enumerate(mesh.edge_lines):
                        if i in seen.get("edge", ()) or hit(pl):
                            picks.append(Pick("edge", b.id, i))
                else:
                    pos = mesh.positions[::max(1, len(mesh.positions) // 4000)]
                    if seen or hit(pos):
                        picks.append(Pick("body", b.id))
        additive = bool(mods & (Qt.ShiftModifier | Qt.ControlModifier)) or self.filter is not None
        sel = list(self.selection) if additive else []
        for p in picks:
            if p not in sel:
                sel.append(p)
        self.selection = sel
        self.scene_dirty = True
        self.selection_changed.emit()
        self.status.emit(f"{len(picks)} item(s) selected ({'crossing' if crossing else 'window'})")

    def _ids_in_rect(self, lo, hi):
        """Visible pickable elements inside a screen rectangle (crossing select)."""
        self._render_pick()
        self.makeCurrent()
        dpr = self._dpr()
        H = int(self.height() * dpr)
        cx, cy = (lo + hi) / 2 * dpr
        rad = int(max(hi - lo) / 2 * dpr) + 1
        ids, _, (x0, y0) = self.r.read_pick(int(cx), int(cy), H, rad)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        out: dict = {}
        if ids is None:
            return out
        # read_pick returns a square; clip it to the actual rectangle
        ys, xs = np.nonzero(ids)
        for iy, ix in zip(ys, xs):
            px, py = (ix + x0) / dpr, (H - 1 - (iy + y0)) / dpr
            if not (lo[0] <= px <= hi[0] and lo[1] <= py <= hi[1]):
                continue
            res = self.reg.lookup(int(ids[iy, ix]))
            if res is None:
                continue
            kind, key, local = res
            out.setdefault(key, {}).setdefault(kind, set()).add(local)
        return out

    # ------------------------------------------------------------------ view helpers
    def selection_bounds(self):
        los, his = [], []
        st = self.vstate
        for p in self.selection:
            b = st.bodies.get(p.key)
            if b is None:
                continue
            shape = K.faces(b.shape)[p.index] if p.kind == "face" else \
                K.edges(b.shape)[p.index] if p.kind == "edge" else b.shape
            lo, hi = K.bbox(shape)
            los.append(lo)
            his.append(hi)
        if not los:
            return None
        return np.min(los, 0), np.max(his, 0)

    def fit_selection(self):
        bb = self.selection_bounds()
        if bb is None:
            self.fit_all()
            return
        c, d = self.cam.fit(*bb)
        self.cam.start_animation(self.cam.rot, c, d * 1.3)
        self._timer.start()

    # ------------------------------------------------------------------ helpers for tools
    def screen_of(self, world) -> np.ndarray:
        return self.cam.project(world, self._scene_radius)[0][:2]

    def set_previews(self, items):
        self.preview_shapes = items
        self.scene_dirty = True
        self.update()

    def grab_image(self):
        return self.grabFramebuffer()


def _is_plain_number(expr, val, kind):
    try:
        float(expr.replace("mm", "").replace("deg", "").strip())
        return True
    except ValueError:
        return False
