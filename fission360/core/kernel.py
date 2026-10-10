"""Thin, typed wrapper around the OpenCASCADE (OCCT) B-rep kernel.

Everything that touches OCP lives here so the rest of the application can
work with numpy arrays, plain Python data and opaque ``TopoDS_Shape``
handles.  Boolean operations run with OCCT's parallel mode and a small fuzzy
tolerance, and results are cleaned with ``UnifySameDomain`` so that faces
split by booleans merge back -- the model topology stays as tidy as in
commercial modellers.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass

import numpy as np
from OCP.BOPAlgo import BOPAlgo_Builder
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import (BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse,
                             BRepAlgoAPI_Splitter)
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepLib import BRepLib
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepOffsetAPI import (BRepOffsetAPI_MakePipeShell, BRepOffsetAPI_MakeThickSolid,
                               BRepOffsetAPI_ThruSections, BRepOffsetAPI_DraftAngle)
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism,
                             BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeTorus,
                             BRepPrimAPI_MakeCone)
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.GC import GC_MakeArcOfCircle
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import (GeomAbs_BSplineSurface, GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder,
                         GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus)
from OCP.GeomAPI import GeomAPI_Interpolate
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.ShapeFix import ShapeFix_Shape
from OCP.StlAPI import StlAPI_Reader, StlAPI_Writer
from OCP.collections import HArray1_gp_Pnt as TColgp_HArray1OfPnt
from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_INTERNAL,
                        TopAbs_ON, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX,
                        TopAbs_WIRE)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.collections import List_TopoDS_Shape
from OCP.gp import (gp_Ax1, gp_Ax2, gp_Ax3, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d, gp_Trsf,
                    gp_Vec)

FUZZY = 1e-5


def _quiet_occt():
    """Silence OCCT's console printer (STEP/IGES transfer statistics)."""
    if os.environ.get("FISSION360_OCCT_VERBOSE"):
        return
    try:
        from OCP.Message import Message, Message_Gravity
        for p in list(Message.DefaultMessenger_s().Printers()):
            p.SetTraceLevel(Message_Gravity.Message_Fail)
    except Exception:
        pass


_quiet_occt()


class KernelError(Exception):
    pass


# ---------------------------------------------------------------------------
# Small conversions
# ---------------------------------------------------------------------------

def P(v) -> gp_Pnt:
    return gp_Pnt(float(v[0]), float(v[1]), float(v[2]))


def D(v) -> gp_Dir:
    return gp_Dir(float(v[0]), float(v[1]), float(v[2]))


def V(v) -> gp_Vec:
    return gp_Vec(float(v[0]), float(v[1]), float(v[2]))


def np3(p) -> np.ndarray:
    return np.array([p.X(), p.Y(), p.Z()])


@dataclass
class Frame:
    """A right-handed coordinate frame used for sketch planes."""
    origin: np.ndarray
    xdir: np.ndarray
    normal: np.ndarray

    def __post_init__(self):
        self.origin = np.asarray(self.origin, float)
        n = np.asarray(self.normal, float)
        self.normal = n / np.linalg.norm(n)
        x = np.asarray(self.xdir, float)
        x = x - np.dot(x, self.normal) * self.normal
        self.xdir = x / np.linalg.norm(x)

    @property
    def ydir(self) -> np.ndarray:
        return np.cross(self.normal, self.xdir)

    def to_world(self, uv) -> np.ndarray:
        uv = np.asarray(uv, float)
        return self.origin + np.multiply.outer(uv[..., 0], self.xdir) + np.multiply.outer(uv[..., 1], self.ydir)

    def to_local(self, p) -> np.ndarray:
        d = np.asarray(p, float) - self.origin
        return np.stack([d @ self.xdir, d @ self.ydir], axis=-1)

    def ax3(self) -> gp_Ax3:
        return gp_Ax3(P(self.origin), D(self.normal), D(self.xdir))

    def pln(self) -> gp_Pln:
        return gp_Pln(self.ax3())

    def matrix(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = self.xdir, self.ydir, self.normal, self.origin
        return m

    def to_dict(self):
        return {"o": self.origin.tolist(), "x": self.xdir.tolist(), "n": self.normal.tolist()}

    @staticmethod
    def from_dict(d):
        return Frame(d["o"], d["x"], d["n"])

    def offset(self, dist: float) -> "Frame":
        return Frame(self.origin + self.normal * dist, self.xdir, self.normal)


ORIGIN_FRAMES = {
    "XY": Frame([0, 0, 0], [1, 0, 0], [0, 0, 1]),
    "XZ": Frame([0, 0, 0], [1, 0, 0], [0, -1, 0]),
    "YZ": Frame([0, 0, 0], [0, 1, 0], [1, 0, 0]),
}
ORIGIN_AXES = {"X": ([0, 0, 0], [1, 0, 0]), "Y": ([0, 0, 0], [0, 1, 0]), "Z": ([0, 0, 0], [0, 0, 1])}


# ---------------------------------------------------------------------------
# Topology helpers
# ---------------------------------------------------------------------------

def subshapes(shape: TopoDS_Shape, kind) -> list:
    """Unique sub-shapes in a deterministic order (indexed map)."""
    if shape is None or shape.IsNull():
        return []
    m = ShapeMap()
    TopExp.MapShapes_s(shape, kind, m)
    cast = {TopAbs_FACE: TopoDS.Face, TopAbs_EDGE: TopoDS.Edge, TopAbs_VERTEX: TopoDS.Vertex,
            TopAbs_SOLID: TopoDS.Solid, TopAbs_WIRE: TopoDS.Wire, TopAbs_SHELL: TopoDS.Shell}[kind]
    return [cast(m.FindKey(i)) for i in range(1, m.Size() + 1)]


def faces(shape):
    return subshapes(shape, TopAbs_FACE)


def edges(shape):
    return subshapes(shape, TopAbs_EDGE)


def vertices(shape):
    return subshapes(shape, TopAbs_VERTEX)


def solids(shape):
    return subshapes(shape, TopAbs_SOLID)


def compound(shapes) -> TopoDS_Shape:
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        if s is not None and not s.IsNull():
            b.Add(c, s)
    return c


def to_list(shapes) -> List_TopoDS_Shape:
    lst = List_TopoDS_Shape()
    for s in shapes:
        lst.Append(s)
    return lst


def is_valid(shape) -> bool:
    return shape is not None and not shape.IsNull() and BRepCheck_Analyzer(shape).IsValid()


def bbox(shape) -> tuple[np.ndarray, np.ndarray]:
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b, True)
    if b.IsVoid():
        return np.zeros(3), np.zeros(3)
    return np3(b.CornerMin()), np3(b.CornerMax())


def vertex_point(v) -> np.ndarray:
    return np3(BRep_Tool.Pnt_s(v))


# ---------------------------------------------------------------------------
# Sketch -> topology
# ---------------------------------------------------------------------------

def sketch_edges(sketch, frame: Frame, include_construction=False) -> list[tuple[int, TopoDS_Shape]]:
    """Build 3D edges for the sketch curves.  Returns (entity id, edge)."""
    out = []
    for e in sketch.curves(include_construction):
        try:
            edge = curve_edge(sketch, e, frame)
        except Exception:  # degenerate geometry (zero-length line, etc.)
            continue
        if edge is not None:
            out.append((e.id, edge))
    return out


def curve_edge(sketch, e, frame: Frame):
    W = lambda uv: P(frame.to_world(uv))  # noqa: E731
    if e.kind == "line":
        a, b = sketch.xy(e.pts[0]), sketch.xy(e.pts[1])
        if math.dist(a, b) < 1e-7:
            return None
        return BRepBuilderAPI_MakeEdge(W(a), W(b)).Edge()
    if e.kind in ("circle", "arc"):
        if e.r < 1e-7:
            return None
        c = sketch.xy(e.pts[0])
        ax2 = gp_Ax2(W(c), D(frame.normal), D(frame.xdir))
        circ = gp_Circ(ax2, e.r)
        if e.kind == "circle":
            return BRepBuilderAPI_MakeEdge(circ).Edge()
        a0, a1 = sketch.arc_angles(e)
        arc = GC_MakeArcOfCircle(circ, a0, a1, True).Value()
        return BRepBuilderAPI_MakeEdge(arc).Edge()
    if e.kind == "spline":
        pts = [sketch.xy(p) for p in e.pts]
        if len(pts) < 2:
            return None
        arr = TColgp_HArray1OfPnt(1, len(pts))
        for i, p in enumerate(pts):
            arr.SetValue(i + 1, W(p))
        interp = GeomAPI_Interpolate(arr, False, 1e-6)
        interp.Perform()
        if not interp.IsDone():
            return None
        return BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()
    return None


def build_profiles(sketch, frame: Frame) -> list[TopoDS_Shape]:
    """Compute closed regions ("profiles") of a sketch, Fusion-style.

    All non-construction curves split a large planar face with the general
    fuse algorithm; every resulting sub-face that does not touch the outer
    border is a profile.  Nested loops therefore give separate selectable
    regions (ring + inner disc), exactly like Fusion 360.
    """
    es = [e for _, e in sketch_edges(sketch, frame)]
    if not es:
        return []
    lo, hi = bbox(compound(es))
    lo_uv = frame.to_local(lo)
    hi_uv = frame.to_local(hi)
    allp = np.array([lo_uv, hi_uv, frame.to_local([lo[0], hi[1], lo[2]]), frame.to_local([hi[0], lo[1], hi[2]])])
    span = max(float(np.ptp(allp[:, 0])), float(np.ptp(allp[:, 1])), 1.0)
    mn, mx = allp.min(0) - span, allp.max(0) + span
    pln = frame.pln()
    big = BRepBuilderAPI_MakeFace(pln, float(mn[0]), float(mx[0]), float(mn[1]), float(mx[1])).Face()

    bld = BOPAlgo_Builder()
    bld.AddArgument(big)
    for e in es:
        bld.AddArgument(e)
    bld.SetFuzzyValue(FUZZY)
    bld.SetRunParallel(True)
    bld.Perform()
    if bld.HasErrors():
        return []
    res = bld.Modified(big)
    regions = []
    tol = span * 1e-6
    it = res.cbegin() if hasattr(res, "cbegin") else None
    shapes = list(_iter_list(res))
    for f in shapes:
        f = TopoDS.Face(f)
        flo, fhi = bbox(f)
        uv = frame.to_local(np.array([flo, fhi]))
        if (uv[:, 0].min() <= mn[0] + span * 0.01 or uv[:, 1].min() <= mn[1] + span * 0.01 or
                uv[:, 0].max() >= mx[0] - span * 0.01 or uv[:, 1].max() >= mx[1] - span * 0.01):
            continue  # outer leftover region
        regions.append(_clean_face(f, frame))
    del it, tol
    regions = [r for r in regions if r is not None]
    # Deterministic order: by area descending then centroid
    regions.sort(key=lambda f: (-round(area(f), 6), *np.round(centroid(f), 6)))
    return regions


def _iter_list(lst):
    """Iterate an OCP List_TopoDS_Shape."""
    try:
        for s in lst:
            yield s
    except TypeError:
        from OCP.TopTools import TopTools_ListIteratorOfListOfShape  # pragma: no cover
        it = TopTools_ListIteratorOfListOfShape(lst)
        while it.More():
            yield it.Value()
            it.Next()


def _clean_face(face, frame: Frame):
    """Drop dangling/internal edges left inside a region by the splitter."""
    wires = subshapes(face, TopAbs_WIRE)
    has_internal = False
    for w in wires:
        ex = TopExp_Explorer(w, TopAbs_EDGE)
        while ex.More():
            if ex.Current().Orientation() == TopAbs_INTERNAL:
                has_internal = True
            ex.Next()
    if not has_internal:
        return face
    outer = BRepTools.OuterWire_s(face)
    mk = None
    for w in [outer] + [w for w in wires if not w.IsSame(outer)]:
        wb = BRepBuilderAPI_MakeWire()
        ex = TopExp_Explorer(w, TopAbs_EDGE)
        n = 0
        while ex.More():
            if ex.Current().Orientation() != TopAbs_INTERNAL:
                wb.Add(TopoDS.Edge(ex.Current()))
                n += 1
            ex.Next()
        if n == 0 or not wb.IsDone():
            continue
        wire = wb.Wire()
        if not BRep_Tool.IsClosed_s(wire):
            continue
        if mk is None:
            mk = BRepBuilderAPI_MakeFace(frame.pln(), wire, True)
        else:
            mk.Add(wire)
    if mk is None or not mk.IsDone():
        return None
    f = mk.Face()
    sf = ShapeFix_Shape(f)
    sf.Perform()
    return TopoDS.Face(sf.Shape()) if sf.Shape().ShapeType() == TopAbs_FACE else f


def face_contains(face, frame: Frame, uv) -> bool:
    p = frame.to_world(uv)
    surf_pt = gp_Pnt(*p)
    from OCP.BRepClass import BRepClass_FaceClassifier as FC
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    srf = BRep_Tool.Surface_s(face)
    proj = GeomAPI_ProjectPointOnSurf(surf_pt, srf)
    if proj.NbPoints() == 0:
        return False
    u, v = proj.LowerDistanceParameters()
    cls = FC(face, gp_Pnt2d(u, v), 1e-6)
    return cls.State() in (TopAbs_IN,)


def profile_at(profiles, frame: Frame, uv):
    """Smallest profile containing ``uv`` (handles nested regions)."""
    hits = [f for f in profiles if face_contains(f, frame, uv)]
    if not hits:
        return None
    return min(hits, key=area)


def interior_point(face, frame: Frame) -> tuple[float, float]:
    """A point strictly inside a planar face (in sketch coordinates)."""
    c = frame.to_local(centroid(face))
    if face_contains(face, frame, c):
        return float(c[0]), float(c[1])
    # Fall back: sample a triangulation and use the largest triangle's centre
    BRepMesh_IncrementalMesh(face, 0.5, False, 0.5, False)
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is None:
        return float(c[0]), float(c[1])
    best, bp = -1.0, c
    for i in range(1, tri.NbTriangles() + 1):
        a, b, cc = tri.Triangle(i).Get()
        pa, pb, pc = (np3(tri.Node(k)) for k in (a, b, cc))
        ar = np.linalg.norm(np.cross(pb - pa, pc - pa))
        if ar > best:
            best, bp = ar, frame.to_local((pa + pb + pc) / 3)
    return float(bp[0]), float(bp[1])


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

def area(face) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return g.Mass()


def centroid(shape) -> np.ndarray:
    g = GProp_GProps()
    st = shape.ShapeType()
    if st in (TopAbs_SOLID, TopAbs_COMPOUND) and solids(shape):
        BRepGProp.VolumeProperties_s(shape, g)
    elif st == TopAbs_EDGE:
        BRepGProp.LinearProperties_s(shape, g)
    else:
        BRepGProp.SurfaceProperties_s(shape, g)
    return np3(g.CentreOfMass())


def mass_properties(shape, density_g_cm3: float = 1.0) -> dict:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    vol = g.Mass()
    gs = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, gs)
    c = np3(g.CentreOfMass()) if vol > 0 else np.zeros(3)
    lo, hi = bbox(shape)
    return {"volume_mm3": vol, "area_mm2": gs.Mass(), "mass_g": vol / 1000.0 * density_g_cm3,
            "center_of_mass": c.tolist(), "bbox_min": lo.tolist(), "bbox_max": hi.tolist()}


def distance(a, b) -> tuple[float, np.ndarray, np.ndarray]:
    d = BRepExtrema_DistShapeShape(a, b)
    d.Perform()
    if not d.IsDone() or d.NbSolution() == 0:
        raise KernelError("distance computation failed")
    return d.Value(), np3(d.PointOnShape1(1)), np3(d.PointOnShape2(1))


def face_info(face) -> dict:
    """Geometric signature of a face for references & UI."""
    s = BRepAdaptor_Surface(face)
    t = s.GetType()
    u0, u1, v0, v1 = s.FirstUParameter(), s.LastUParameter(), s.FirstVParameter(), s.LastVParameter()
    um, vm = (u0 + u1) / 2, (v0 + v1) / 2
    props = BRepGProp_Face(face)
    pnt, nrm = gp_Pnt(), gp_Vec()
    props.Normal(um, vm, pnt, nrm)
    n = np3(nrm)
    if np.linalg.norm(n) > 1e-12:
        n = n / np.linalg.norm(n)
    kind = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone",
            GeomAbs_Sphere: "sphere", GeomAbs_Torus: "torus", GeomAbs_BSplineSurface: "bspline"}.get(t, "other")
    info = {"type": kind, "center": centroid(face).tolist(), "normal": n.tolist(), "area": area(face)}
    if kind == "plane":
        pl = s.Plane()
        info["normal"] = np3(pl.Axis().Direction()).tolist()
        if face.Orientation() == TopAbs_REVERSED:
            info["normal"] = (-np.array(info["normal"])).tolist()
        info["xdir"] = np3(pl.XAxis().Direction()).tolist()
    elif kind in ("cylinder", "cone"):
        ax = s.Cylinder().Axis() if kind == "cylinder" else s.Cone().Axis()
        info["axis_origin"] = np3(ax.Location()).tolist()
        info["axis_dir"] = np3(ax.Direction()).tolist()
        if kind == "cylinder":
            info["radius"] = s.Cylinder().Radius()
    return info


def edge_info(edge) -> dict:
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    mid = c.Value((t0 + t1) / 2)
    d = gp_Vec()
    pt = gp_Pnt()
    c.D1((t0 + t1) / 2, pt, d)
    tan = np3(d)
    if np.linalg.norm(tan) > 1e-12:
        tan /= np.linalg.norm(tan)
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, g)
    kind = {GeomAbs_Line: "line", GeomAbs_Circle: "circle"}.get(c.GetType(), "curve")
    info = {"type": kind, "mid": np3(mid).tolist(), "tangent": tan.tolist(), "length": g.Mass(),
            "start": np3(c.Value(t0)).tolist(), "end": np3(c.Value(t1)).tolist()}
    if kind == "circle":
        circ = c.Circle()
        info["center"] = np3(circ.Location()).tolist()
        info["axis"] = np3(circ.Axis().Direction()).tolist()
        info["radius"] = circ.Radius()
    return info


def planar_face_frame(face) -> Frame:
    info = face_info(face)
    if info["type"] != "plane":
        raise KernelError("face is not planar")
    n = np.array(info["normal"])
    x = np.array(info["xdir"])
    # project centroid as origin keeps sketch coordinates small
    return Frame(info["center"], x, n)


# ---------------------------------------------------------------------------
# Modelling operations
# ---------------------------------------------------------------------------

def _check(builder, what: str):
    if hasattr(builder, "HasErrors") and builder.HasErrors():
        raise KernelError(f"{what} failed")
    if hasattr(builder, "IsDone") and not builder.IsDone():
        raise KernelError(f"{what} failed")


def unify(shape):
    try:
        u = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
        u.Build()
        return u.Shape()
    except Exception:
        return shape


def _bool(cls, a, b, what):
    op = cls()
    op.SetArguments(to_list([a]))
    op.SetTools(to_list(b if isinstance(b, (list, tuple)) else [b]))
    op.SetFuzzyValue(FUZZY)
    op.SetRunParallel(True)
    op.SetNonDestructive(True)
    op.Build()
    _check(op, what)
    return unify(op.Shape())


def fuse(a, b):
    return _bool(BRepAlgoAPI_Fuse, a, b, "Join")


def cut(a, b):
    return _bool(BRepAlgoAPI_Cut, a, b, "Cut")


def common(a, b):
    return _bool(BRepAlgoAPI_Common, a, b, "Intersect")


def split(shape, tools):
    sp = BRepAlgoAPI_Splitter()
    sp.SetArguments(to_list([shape]))
    sp.SetTools(to_list(tools))
    sp.SetFuzzyValue(FUZZY)
    sp.SetRunParallel(True)
    sp.Build()
    _check(sp, "Split")
    return solids(sp.Shape())


def prism(face_or_faces, vec) -> TopoDS_Shape:
    shape = compound(face_or_faces) if isinstance(face_or_faces, (list, tuple)) else face_or_faces
    mk = BRepPrimAPI_MakePrism(shape, V(vec), True)
    mk.Build()
    _check(mk, "Extrude")
    return mk.Shape()


def tapered_prism(face, vec, taper_rad: float):
    """Extrude with draft: build straight prism then draft the side faces."""
    straight = prism(face, vec)
    if abs(taper_rad) < 1e-9:
        return straight
    n = np.asarray(vec, float)
    n = n / np.linalg.norm(n)
    base_pln = gp_Pln(P(centroid(face)), D(n))
    draft = BRepOffsetAPI_DraftAngle(straight)
    caps = []
    for f in faces(straight):
        fi = face_info(f)
        if fi["type"] == "plane" and abs(abs(np.dot(fi["normal"], n)) - 1) < 1e-6:
            caps.append(f)
            continue
        draft.Add(f, D(n), -taper_rad, base_pln, True)
        if not draft.AddDone():
            raise KernelError("taper angle not possible for this profile")
    draft.Build()
    _check(draft, "Taper")
    return draft.Shape()


def revolve(face_or_faces, axis_origin, axis_dir, angle_rad) -> TopoDS_Shape:
    shape = compound(face_or_faces) if isinstance(face_or_faces, (list, tuple)) else face_or_faces
    mk = BRepPrimAPI_MakeRevol(shape, gp_Ax1(P(axis_origin), D(axis_dir)), float(angle_rad), True)
    mk.Build()
    _check(mk, "Revolve")
    return mk.Shape()


def wire_from_edges(es):
    """Connect edges into a wire (orders them via the wire builder)."""
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.collections import HSequence_TopoDS_Shape as TopTools_HSequenceOfShape
    seq = TopTools_HSequenceOfShape()
    for e in es:
        seq.Append(e)
    wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(seq, 1e-4, False)
    if wires.Length() < 1:
        raise KernelError("could not connect path edges")
    return TopoDS.Wire(wires.Value(1))


def sweep(face, path_wire, frenet=True):
    outer = BRepTools.OuterWire_s(face)
    mk = BRepOffsetAPI_MakePipeShell(path_wire)
    mk.SetMode(frenet)
    mk.Add(outer, False, True)
    mk.Build()
    _check(mk, "Sweep")
    mk.MakeSolid()
    solid = mk.Shape()
    # Inner loops (holes) are swept separately and subtracted
    for w in subshapes(face, TopAbs_WIRE):
        if w.IsSame(outer):
            continue
        mi = BRepOffsetAPI_MakePipeShell(path_wire)
        mi.SetMode(frenet)
        mi.Add(w, False, True)
        mi.Build()
        if mi.IsDone():
            mi.MakeSolid()
            solid = cut(solid, mi.Shape())
    return solid


def loft(sections, solid=True, ruled=False):
    mk = BRepOffsetAPI_ThruSections(solid, ruled, 1e-6)
    for s in sections:
        if s.ShapeType() == TopAbs_FACE:
            mk.AddWire(BRepTools.OuterWire_s(TopoDS.Face(s)))
        elif s.ShapeType() == TopAbs_WIRE:
            mk.AddWire(TopoDS.Wire(s))
        elif s.ShapeType() == TopAbs_VERTEX:
            mk.AddVertex(TopoDS.Vertex(s))
    mk.CheckCompatibility(True)
    mk.Build()
    _check(mk, "Loft")
    return mk.Shape()


def fillet(shape, edge_list, radius):
    mk = BRepFilletAPI_MakeFillet(shape)
    for e in edge_list:
        mk.Add(float(radius), e)
    mk.Build()
    _check(mk, "Fillet")
    return mk.Shape()


def chamfer(shape, edge_list, dist, dist2=None):
    mk = BRepFilletAPI_MakeChamfer(shape)
    for e in edge_list:
        if dist2 is None:
            mk.Add(float(dist), e)
        else:
            # two-distance chamfer needs a reference face adjacent to the edge
            f = _adjacent_face(shape, e)
            mk.Add(float(dist), float(dist2), e, f)
    mk.Build()
    _check(mk, "Chamfer")
    return mk.Shape()


def _adjacent_face(shape, edge):
    for f in faces(shape):
        for e in edges(f):
            if e.IsSame(edge):
                return f
    raise KernelError("edge has no adjacent face")


def shell(shape, open_faces, thickness, inside=True):
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, to_list(open_faces), -float(thickness) if inside else float(thickness), 1e-4)
    mk.Build()
    _check(mk, "Shell")
    return mk.Shape()


def transform(shape, matrix: np.ndarray, copy=True):
    t = gp_Trsf()
    m = matrix
    t.SetValues(*[float(m[i, j]) for i in range(3) for j in range(4)])
    return BRepBuilderAPI_Transform(shape, t, copy).Shape()


def translate(shape, vec, copy=True):
    t = gp_Trsf()
    t.SetTranslation(V(vec))
    return BRepBuilderAPI_Transform(shape, t, copy).Shape()


def rotate(shape, origin, axis, angle_rad, copy=True):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(P(origin), D(axis)), float(angle_rad))
    return BRepBuilderAPI_Transform(shape, t, copy).Shape()


def mirror(shape, origin, normal, copy=True):
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(P(origin), D(normal)))
    return BRepBuilderAPI_Transform(shape, t, copy).Shape()


def scale(shape, origin, factor, copy=True):
    t = gp_Trsf()
    t.SetScale(P(origin), float(factor))
    return BRepBuilderAPI_Transform(shape, t, copy).Shape()


def box(frame: Frame, x, y, w, l, h):
    ax2 = gp_Ax2(P(frame.to_world((x, y))), D(frame.normal), D(frame.xdir))
    if h < 0:
        ax2 = gp_Ax2(P(frame.to_world((x, y)) + frame.normal * h), D(frame.normal), D(frame.xdir))
        h = -h
    return BRepPrimAPI_MakeBox(ax2, float(w), float(l), float(h)).Shape()


def cylinder(frame: Frame, x, y, r, h):
    base = frame.to_world((x, y))
    if h < 0:
        base, h = base + frame.normal * h, -h
    return BRepPrimAPI_MakeCylinder(gp_Ax2(P(base), D(frame.normal), D(frame.xdir)), float(r), float(h)).Shape()


def cone(frame: Frame, x, y, r1, r2, h):
    return BRepPrimAPI_MakeCone(gp_Ax2(P(frame.to_world((x, y))), D(frame.normal), D(frame.xdir)),
                                float(r1), float(r2), float(h)).Shape()


def sphere(center, r):
    return BRepPrimAPI_MakeSphere(P(center), float(r)).Shape()


def torus(frame: Frame, x, y, R, r):
    return BRepPrimAPI_MakeTorus(gp_Ax2(P(frame.to_world((x, y))), D(frame.normal), D(frame.xdir)),
                                 float(R), float(r)).Shape()


def coil(frame: Frame, x, y, radius, pitch, turns, section_r):
    """Helical coil swept with a circular section."""
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Line
    from OCP.gp import gp_Dir2d
    ax3 = gp_Ax3(P(frame.to_world((x, y))), D(frame.normal), D(frame.xdir))
    surf = Geom_CylindricalSurface(ax3, float(radius))
    line = Geom2d_Line(gp_Pnt2d(0, 0), gp_Dir2d(2 * math.pi, pitch))
    length = math.hypot(2 * math.pi, pitch) * turns
    edge = BRepBuilderAPI_MakeEdge(line, surf, 0.0, length).Edge()
    BRepLib.BuildCurves3d_s(edge)
    path = BRepBuilderAPI_MakeWire(edge).Wire()
    start = frame.to_world((x + radius, y))
    c = BRepAdaptor_Curve(edge)
    pt, tan = gp_Pnt(), gp_Vec()
    c.D1(c.FirstParameter(), pt, tan)
    circ = gp_Circ(gp_Ax2(P(start), gp_Dir(tan)), float(section_r))
    prof = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circ).Edge()).Wire()
    face = BRepBuilderAPI_MakeFace(prof).Face()
    mk = BRepOffsetAPI_MakePipeShell(path)
    mk.SetMode(False)
    mk.SetMode(gp_Dir(*frame.normal))  # binormal mode keeps the section upright
    mk.Add(BRepTools.OuterWire_s(face), False, False)
    mk.Build()
    _check(mk, "Coil")
    mk.MakeSolid()
    return mk.Shape()


def hole(frame_origin, direction, diameter, depth, cbore_d=0.0, cbore_depth=0.0, tip_angle_deg=118.0):
    """Tool body for a (counterbored) drilled hole; subtract it from a body."""
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    o = np.asarray(frame_origin, float)
    r = diameter / 2
    tool = BRepPrimAPI_MakeCylinder(gp_Ax2(P(o - d * 0.01), D(d)), r, depth + 0.01).Shape()
    if tip_angle_deg and tip_angle_deg < 180:
        h = r / math.tan(math.radians(tip_angle_deg) / 2)
        tip = BRepPrimAPI_MakeCone(gp_Ax2(P(o + d * depth), D(d)), r, 0.0, h).Shape()
        tool = fuse(tool, tip)
    if cbore_d > diameter and cbore_depth > 0:
        cb = BRepPrimAPI_MakeCylinder(gp_Ax2(P(o - d * 0.01), D(d)), cbore_d / 2, cbore_depth + 0.01).Shape()
        tool = fuse(tool, cb)
    return tool


def thicken(face_shape, thickness):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    mk = BRepOffsetAPI_MakeOffsetShape()
    mk.PerformByJoin(face_shape, float(thickness), 1e-4)
    mk.Build()
    _check(mk, "Thicken")
    off = mk.Shape()
    return loft_between(face_shape, off)


def loft_between(a, b):
    fa, fb = faces(a), faces(b)
    out = []
    for x, y in zip(fa, fb):
        out.append(loft([x, y]))
    return compound(out) if len(out) > 1 else out[0]


def offset_face_wire(face, dist):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Arc
    mk = BRepOffsetAPI_MakeOffset(face, GeomAbs_Arc)
    mk.Perform(float(dist))
    _check(mk, "Offset")
    return mk.Shape()


# ---------------------------------------------------------------------------
# Tessellation for display
# ---------------------------------------------------------------------------

@dataclass
class Mesh:
    positions: np.ndarray   # (N,3) float32
    normals: np.ndarray     # (N,3) float32
    indices: np.ndarray     # (M,3) uint32
    face_of_tri: np.ndarray  # (M,) int32  -> face index (0-based)
    edge_lines: list        # per edge: (K,3) float32 polyline
    vertex_points: np.ndarray  # (V,3)
    face_count: int


def tessellate(shape, lin_defl: float | None = None, ang_defl: float = 0.35) -> Mesh:
    """Triangulate a shape for display.  Deflection adapts to model size."""
    lo, hi = bbox(shape)
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    if lin_defl is None:
        lin_defl = max(diag * 8e-4, 1e-3)
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)

    pos_chunks, nrm_chunks, idx_chunks, fid_chunks = [], [], [], []
    base = 0
    fl = faces(shape)
    for fi, face in enumerate(fl):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        nn, nt = tri.NbNodes(), tri.NbTriangles()
        if not tri.HasNormals():
            tri.ComputeNormals()
        trsf = loc.Transformation()
        identity = loc.IsIdentity()
        pts = np.empty((nn, 3))
        nrm = np.empty((nn, 3))
        for i in range(1, nn + 1):
            p = tri.Node(i)
            if not identity:
                p = p.Transformed(trsf)
            pts[i - 1] = (p.X(), p.Y(), p.Z())
            n = tri.Normal(i)
            nrm[i - 1] = (n.X(), n.Y(), n.Z())
        if not identity:
            R = np.array([[trsf.Value(r, c) for c in (1, 2, 3)] for r in (1, 2, 3)])
            nrm = nrm @ R.T
        tris = np.array([tri.Triangle(i).Get() for i in range(1, nt + 1)], dtype=np.int64) - 1
        if face.Orientation() == TopAbs_REVERSED:
            tris = tris[:, ::-1]
            nrm = -nrm
        pos_chunks.append(pts)
        nrm_chunks.append(nrm)
        idx_chunks.append(tris + base)
        fid_chunks.append(np.full(nt, fi, np.int32))
        base += nn

    edge_lines = []
    for e in edges(shape):
        try:
            c = BRepAdaptor_Curve(e)
            disc = GCPnts_QuasiUniformDeflection(c, lin_defl * 0.5)
            if not disc.IsDone() or disc.NbPoints() < 2:
                raise ValueError
            pl = np.array([np3(disc.Value(i)) for i in range(1, disc.NbPoints() + 1)], np.float32)
        except Exception:
            pl = np.zeros((0, 3), np.float32)
        edge_lines.append(pl)

    verts = np.array([vertex_point(v) for v in vertices(shape)], np.float32).reshape(-1, 3)
    if pos_chunks:
        positions = np.vstack(pos_chunks).astype(np.float32)
        normals = np.vstack(nrm_chunks).astype(np.float32)
        indices = np.vstack(idx_chunks).astype(np.uint32)
        fot = np.concatenate(fid_chunks)
    else:
        positions = normals = np.zeros((0, 3), np.float32)
        indices = np.zeros((0, 3), np.uint32)
        fot = np.zeros(0, np.int32)
    return Mesh(positions, normals, indices, fot, edge_lines, verts, len(fl))


def edge_polyline(edge, defl=0.05) -> np.ndarray:
    c = BRepAdaptor_Curve(edge)
    disc = GCPnts_QuasiUniformDeflection(c, defl)
    return np.array([np3(disc.Value(i)) for i in range(1, disc.NbPoints() + 1)], np.float32)


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------

def export_step(shapes_with_names, path: str):
    w = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    for _, s in shapes_with_names:
        if w.Transfer(s, STEPControl_AsIs) != IFSelect_RetDone:
            raise KernelError("STEP transfer failed")
    if w.Write(path) != IFSelect_RetDone:
        raise KernelError("STEP write failed")


def export_iges(shapes, path: str):
    w = IGESControl_Writer("MM", 1)
    for s in shapes:
        w.AddShape(s)
    w.ComputeModel()
    if not w.Write(path):
        raise KernelError("IGES write failed")


def export_stl(shape, path: str, lin_defl: float = 0.01, ang_defl: float = 0.2, ascii=False):
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
    w = StlAPI_Writer()
    w.ASCIIMode = ascii
    if not w.Write(shape, path):
        raise KernelError("STL write failed")


def export_brep(shape, path: str):
    BRepTools.Write_s(shape, path)


def import_step(path: str) -> list[TopoDS_Shape]:
    r = STEPControl_Reader()
    if r.ReadFile(path) != IFSelect_RetDone:
        raise KernelError("cannot read STEP file")
    r.TransferRoots()
    s = r.OneShape()
    return solids(s) or [s]


def import_iges(path: str) -> list[TopoDS_Shape]:
    r = IGESControl_Reader()
    if r.ReadFile(path) != IFSelect_RetDone:
        raise KernelError("cannot read IGES file")
    r.TransferRoots()
    s = r.OneShape()
    return solids(s) or [s]


def import_stl(path: str) -> list[TopoDS_Shape]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    shp = TopoDS_Shape()
    if not StlAPI_Reader().Read(shp, path):
        raise KernelError("cannot read STL file")
    try:
        shells = subshapes(shp, TopAbs_SHELL)
        if shells:
            mk = BRepBuilderAPI_MakeSolid(shells[0])
            if mk.IsDone():
                return [unify(mk.Solid())]
    except Exception:
        pass
    return [shp]


def import_brep(path: str) -> list[TopoDS_Shape]:
    s = TopoDS_Shape()
    if not BRepTools.Read_s(s, path, BRep_Builder()):
        raise KernelError("cannot read BREP file")
    return solids(s) or [s]


def shape_to_bytes(shape) -> bytes:
    fd, p = tempfile.mkstemp(suffix=".brep")
    os.close(fd)
    try:
        BRepTools.Write_s(shape, p)
        with open(p, "rb") as f:
            return f.read()
    finally:
        os.unlink(p)


def shape_from_bytes(data: bytes):
    fd, p = tempfile.mkstemp(suffix=".brep")
    os.close(fd)
    try:
        with open(p, "wb") as f:
            f.write(data)
        s = TopoDS_Shape()
        BRepTools.Read_s(s, p, BRep_Builder())
        return s
    finally:
        os.unlink(p)


def face_normal_at(face, point) -> np.ndarray:
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    srf = BRep_Tool.Surface_s(face)
    proj = GeomAPI_ProjectPointOnSurf(P(point), srf)
    u, v = proj.LowerDistanceParameters()
    props = BRepGProp_Face(face)
    pnt, nrm = gp_Pnt(), gp_Vec()
    props.Normal(u, v, pnt, nrm)
    n = np3(nrm)
    return n / (np.linalg.norm(n) or 1)
