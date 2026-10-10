"""2D drawings: orthographic views with hidden-line removal, sheet layout, SVG / DXF output.

Views are projected with OpenCASCADE's polygon-free HLR algorithm (exact
visible/hidden edges), then discretised.  The sheet uses third-angle
projection like Fusion's default drawing template: top above the front
view, right view beside it.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import numpy as np
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

from .core import kernel as K

SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "Letter": (279.4, 215.9)}
STANDARD_SCALES = [(1, 100), (1, 50), (1, 20), (1, 10), (1, 5), (1, 2), (1, 1), (2, 1), (5, 1), (10, 1)]

# view name -> (viewer direction N pointing at the viewer, x axis of the view)
VIEWS = {
    "front": ((0, -1, 0), (1, 0, 0)),
    "back": ((0, 1, 0), (-1, 0, 0)),
    "top": ((0, 0, 1), (1, 0, 0)),
    "bottom": ((0, 0, -1), (1, 0, 0)),
    "right": ((1, 0, 0), (0, 1, 0)),
    "left": ((-1, 0, 0), (0, -1, 0)),
    "iso": ((1, -1, 1), (1, 1, 0)),
    "section": ((0, -1, 0), (1, 0, 0)),     # front view of the half behind the XZ cut plane
}


@dataclass
class View:
    name: str
    visible: list = field(default_factory=list)   # polylines (N, 2) in model mm
    hidden: list = field(default_factory=list)
    marks: list = field(default_factory=list)     # centre lines / marks: 2-point polylines
    notes: list = field(default_factory=list)     # (text, anchor xy, label xy) callouts, model mm
    hatch: list = field(default_factory=list)     # boundary segments (N, 2) of cut faces to hatch
    title: str = ""

    def bounds(self):
        pts = [p for pl in self.visible + self.hidden for p in pl]
        if not pts:
            return np.zeros(2), np.zeros(2)
        a = np.array(pts)
        return a.min(axis=0), a.max(axis=0)


def _to_view(name: str, p):
    n, vx = (np.array(v, float) for v in VIEWS[name])
    n, vx = n / np.linalg.norm(n), vx / np.linalg.norm(vx)
    vy = np.cross(n, vx)
    p = np.asarray(p, float)
    return np.array([float(p @ vx), float(p @ vy)])


def _annotate(view: View, shape, name: str):
    """Centre marks and diameter callouts for every cylindrical hole / boss."""
    n = np.array(VIEWS[name][0], float)
    n /= np.linalg.norm(n)
    seen = set()
    for f in K.faces(shape):
        fi = K.face_info(f)
        if fi["type"] != "cylinder":
            continue
        ax = np.array(fi["axis_dir"])
        org = np.array(fi["axis_origin"])
        r = fi["radius"]
        lo, hi = K.bbox(f)
        ext = float(np.abs(np.dot(hi - lo, np.abs(ax))))
        c = np.array(fi["center"])
        c = org + ax * float(np.dot(c - org, ax))          # on the axis, mid-face
        key = (name, tuple(np.round(c, 3)), round(r, 3), tuple(np.round(np.abs(ax), 3)))
        if key in seen:
            continue
        seen.add(key)
        if name == "iso" or name == "section":
            continue
        along = abs(float(ax @ n))
        c2 = _to_view(name, c)
        if along > 0.99:                                   # seen end-on: circle with a centre cross
            k = max(r * 0.35, 0.8) * 1.0
            view.marks += [np.array([c2 - [r + k, 0], c2 + [r + k, 0]]), np.array([c2 - [0, r + k], c2 + [0, r + k]])]
            view.notes.append((f"\u00d8{2 * r:.4g}", c2 + [r * 0.7071, r * 0.7071], c2 + [r + k + 4, r + k + 4]))
        elif along < 0.01:                                 # side-on: centre line along the axis
            d2 = _to_view(name, c + ax) - c2
            d2 /= np.linalg.norm(d2)
            h = ext / 2 + r * 0.4
            view.marks.append(np.array([c2 - d2 * h, c2 + d2 * h]))


def project(shape, name: str, hidden=True) -> View:
    n, vx = VIEWS[name]
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*n), gp_Dir(*vx))
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    conv = HLRBRep_HLRToShape(algo)

    def lines(*getters):
        out = []
        for g in getters:
            try:
                comp = g()
            except Exception:
                continue
            if comp is None or comp.IsNull():
                continue
            for e in K.edges(comp):
                try:
                    pl = K.edge_polyline(e, 0.02)[:, :2]
                except Exception:
                    continue
                if len(pl) >= 2:
                    out.append(pl)
        return out

    v = View(name)
    if name != "section":
        _annotate(v, shape, name)
    v.visible = lines(conv.VCompound, conv.Rg1LineVCompound, conv.OutLineVCompound)
    if hidden:
        v.hidden = [h for h in lines(conv.HCompound, conv.Rg1LineHCompound, conv.OutLineHCompound)
                    if not _covered(h, v.visible)]
    return v


def _dist_to_polylines(p, polys) -> float:
    best = 1e18
    for pl in polys:
        a, b = pl[:-1], pl[1:]
        ab = b - a
        L = np.maximum((ab * ab).sum(axis=1), 1e-18)
        t = np.clip(((p - a) * ab).sum(axis=1) / L, 0, 1)
        d = np.linalg.norm(a + ab * t[:, None] - p, axis=1).min()
        best = min(best, float(d))
    return best


def _covered(pl, visible, tol=0.02) -> bool:
    """A hidden edge lying exactly under a visible one is not drawn dashed."""
    seg = np.linalg.norm(np.diff(pl, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    probes = [np.array([np.interp(t * cum[-1], cum, pl[:, 0]), np.interp(t * cum[-1], cum, pl[:, 1])])
              for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    return all(_dist_to_polylines(p, visible) < tol for p in probes)


@dataclass
class Dim:
    a: tuple
    b: tuple
    text: str
    vertical: bool = False


@dataclass
class Sheet:
    size: str
    scale: tuple
    placed: list           # (View, ox, oy) origin of the view's lower-left bound in sheet mm (y up)
    dims: list
    title: str


def section_shape(shape, y=None):
    """Keep the half of ``shape`` behind the plane Y=y (default: bounding-box middle) and report the cut faces."""
    lo, hi = K.bbox(shape)
    y = float((lo[1] + hi[1]) / 2) if y is None else y
    big = float(np.linalg.norm(hi - lo)) * 2 + 10
    XY = K.ORIGIN_FRAMES["XY"]
    cutter = K.translate(K.box(XY, lo[0] - big, y - big, 2 * big + (hi[0] - lo[0]), big, 2 * big), (0, 0, lo[2] - big))
    half = K.cut(shape, cutter)
    cut_faces = []
    for f in K.faces(half):
        fi = K.face_info(f)
        if fi["type"] == "plane" and abs(fi["normal"][1] + 1) < 1e-6 and abs(fi["center"][1] - y) < 1e-4:
            cut_faces.append(f)
    return half, cut_faces, y


def hatch_lines(segments, spacing: float):
    """45-degree hatch for the region bounded by the given polylines (even-odd rule)."""
    segs = []
    for pl in segments:
        for a, b in zip(pl[:-1], pl[1:]):
            segs.append((a, b))
    if not segs:
        return []
    allp = np.array([p for sg in segs for p in sg])
    c = allp[:, 1] - allp[:, 0]
    out = []
    for cc in np.arange(np.floor(c.min() / spacing) * spacing + spacing / 2, c.max(), spacing):
        hits = []
        for a, b in segs:
            ca, cb = a[1] - a[0], b[1] - b[0]
            if ca == cb:
                continue
            if (ca <= cc < cb) or (cb <= cc < ca):
                t = (cc - ca) / (cb - ca)
                p = a + (b - a) * t
                hits.append(p[0] + p[1])           # position along the hatch direction
        hits.sort()
        for i in range(0, len(hits) - 1, 2):
            u0, u1 = hits[i], hits[i + 1]
            # point with y - x = cc and x + y = u  ->  x = (u - cc)/2, y = (u + cc)/2
            out.append(np.array([[(u0 - cc) / 2, (u0 + cc) / 2], [(u1 - cc) / 2, (u1 + cc) / 2]]))
    return out


def project_section(shape, y=None) -> View:
    half, faces, y = section_shape(shape, y)
    v = project(half, "section", hidden=False)
    for f in faces:
        for e in K.edges(f):
            try:
                pl = np.array([_to_view("section", q) for q in K.edge_polyline(e, 0.02)])
            except Exception:
                continue
            if len(pl) >= 2:
                v.hatch.append(pl)
    v.title = "SECTION A-A"
    return v


def _choose_layout(views: dict, size: str, margin=14.0, gap=24.0, title_h=26.0):
    """Pick the largest standard scale that fits all views on the sheet; returns (scale, placements)."""
    w, h = SHEETS[size]
    avail_w, avail_h = w - 2 * margin, h - 2 * margin - title_h
    ext = {k: (lambda lo_hi: lo_hi[1] - lo_hi[0])(v.bounds()) for k, v in views.items()}
    front, top, right, iso, sect = (ext.get(k) for k in ("front", "top", "right", "iso", "section"))
    for num, den in reversed(STANDARD_SCALES):
        s = num / den
        # grid: [top] over [front][right]; iso, if any, goes right of top
        col1 = max((e[0] for e in (front, top) if e is not None), default=0) * s
        col2 = max((e[0] for e in (right, iso) if e is not None), default=0) * s
        col3 = (sect[0] * s + gap) if sect is not None else 0
        row1 = (top[1] * s) if top is not None else 0
        row2 = max((e[1] for e in (front, right, sect) if e is not None), default=0) * s
        need_w = col1 + (gap + col2 if col2 else 0) + col3
        need_h = row1 + (gap + row2 if row1 and row2 else row2)
        if need_w <= avail_w and need_h <= avail_h:
            return (num, den), s
    return STANDARD_SCALES[0], STANDARD_SCALES[0][0] / STANDARD_SCALES[0][1]


def make_sheet(shape, name="Part", views=("front", "top", "right"), size="A3", hidden=True,
               dimensions=True) -> Sheet:
    vs = {v: (project_section(shape) if v == "section" else project(shape, v, hidden)) for v in views}
    if "iso" in vs:
        vs["iso"].hidden = []
    scale_t, s = _choose_layout(vs, size)
    w, h = SHEETS[size]
    margin, gap, title_h = 14.0, 24.0, 26.0
    ext = {k: v.bounds() for k, v in vs.items()}
    size_of = lambda k: (ext[k][1] - ext[k][0]) * s   # noqa: E731
    placed, dims = [], []
    # lower-left sheet origin for each view; sheet y grows upward
    base_y = margin + title_h
    row2_h = max((size_of(k)[1] for k in ("front", "right", "section") if k in vs), default=0)
    front_o = (margin, base_y)
    top_o = (margin, base_y + row2_h + gap) if "top" in vs and row2_h else (margin, base_y)
    col1 = max((size_of(k)[0] for k in ("front", "top") if k in vs), default=0)
    right_o = (margin + col1 + gap, base_y)
    iso_o = (margin + col1 + gap, base_y + row2_h + gap if row2_h else base_y)
    col2w = max((size_of(k)[0] for k in ("right", "iso") if k in vs), default=0)
    sect_o = (margin + col1 + gap + (col2w + gap if col2w else 0), base_y)
    origin = {"front": front_o, "top": top_o, "right": right_o, "iso": iso_o, "section": sect_o}
    for k, v in vs.items():
        ox, oy = origin.get(k, (margin, base_y))
        if k == "front" or k == "top":                      # centre narrower views on the column
            ox += (col1 - size_of(k)[0]) / 2
        placed.append((v, ox - ext[k][0][0] * s, oy - ext[k][0][1] * s))   # offset that maps model coords to sheet
    if dimensions:
        for k, v, (ox, oy) in ((k, vs[k], (p[1], p[2])) for p in placed for k in [p[0].name]):
            if k not in ("front", "top", "right", "section"):
                continue
            lo, hi = ext[k]
            x0, x1 = lo[0] * s + ox, hi[0] * s + ox
            y0, y1 = lo[1] * s + oy, hi[1] * s + oy
            dims.append(Dim((x0, y0 - 7), (x1, y0 - 7), f"{(hi[0] - lo[0]):.4g}"))
            dims.append(Dim((x1 + 7, y0), (x1 + 7, y1), f"{(hi[1] - lo[1]):.4g}", vertical=True))
    return Sheet(size, scale_t, placed, dims, name)


# ---------------------------------------------------------------------------- SVG
def write_svg(sheet: Sheet, path: str, author: str = ""):
    w, h = SHEETS[sheet.size]
    s = sheet.scale[0] / sheet.scale[1]
    Y = lambda y: h - y                                      # noqa: E731  (SVG y points down)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">',
           '<style>.v{fill:none;stroke:#111;stroke-width:.5;stroke-linejoin:round;stroke-linecap:round}'
           '.h{fill:none;stroke:#555;stroke-width:.25;stroke-dasharray:3 1.5}'
           '.d{fill:none;stroke:#0a4;stroke-width:.2}.c{fill:none;stroke:#c33;stroke-width:.2;stroke-dasharray:6 1 1 1}.x{fill:none;stroke:#444;stroke-width:.15}.t{font-family:sans-serif;font-size:3.5px;fill:#111}'
           '.big{font-family:sans-serif;font-size:5px;font-weight:bold;fill:#111}</style>',
           f'<rect x="0" y="0" width="{w}" height="{h}" fill="white"/>',
           f'<rect x="7" y="7" width="{w - 14}" height="{h - 14}" fill="none" stroke="#111" stroke-width=".7"/>']

    def poly(pl, ox, oy, cls):
        pts = " ".join(f"{p[0] * s + ox:.3f},{Y(p[1] * s + oy):.3f}" for p in pl)
        out.append(f'<polyline class="{cls}" points="{pts}"/>')

    for view, ox, oy in sheet.placed:
        out.append(f'<g id="{view.name}">')
        for pl in view.hidden:
            poly(pl, ox, oy, "h")
        for pl in view.visible:
            poly(pl, ox, oy, "v")
        for pl in view.marks:
            poly(pl, ox, oy, "c")
        for hl in hatch_lines(view.hatch, 3.0 / s):
            poly(hl, ox, oy, "x")
        for text, anchor, label in view.notes:
            ax_, ay_ = anchor[0] * s + ox, Y(anchor[1] * s + oy)
            lx, ly = label[0] * s + ox, Y(label[1] * s + oy)
            out.append(f'<polyline class="d" points="{ax_:.2f},{ay_:.2f} {lx:.2f},{ly:.2f}"/>')
            out.append(f'<text class="t" x="{lx + 0.8:.2f}" y="{ly:.2f}">{text}</text>')
        lo, hi = view.bounds()
        out.append(f'<text class="t" x="{lo[0] * s + ox:.2f}" y="{Y(lo[1] * s + oy) + 16:.2f}">'
                   f'{view.title or view.name.upper()}</text></g>')
    for d in sheet.dims:
        (ax, ay), (bx, by) = d.a, d.b
        out.append(f'<line class="d" x1="{ax:.2f}" y1="{Y(ay):.2f}" x2="{bx:.2f}" y2="{Y(by):.2f}"/>')
        for px, py in (d.a, d.b):
            t = 1.2
            if d.vertical:
                out.append(f'<line class="d" x1="{px - t:.2f}" y1="{Y(py) - t:.2f}" x2="{px + t:.2f}" y2="{Y(py) + t:.2f}"/>')
            else:
                out.append(f'<line class="d" x1="{px - t:.2f}" y1="{Y(py) + t:.2f}" x2="{px + t:.2f}" y2="{Y(py) - t:.2f}"/>')
        mx, my = (ax + bx) / 2, (ay + by) / 2
        if d.vertical:
            out.append(f'<text class="t" x="{mx + 2.8:.2f}" y="{Y(my):.2f}" transform="rotate(-90 {mx + 2.8:.2f} {Y(my):.2f})" '
                       f'text-anchor="middle">{escape(d.text)}</text>')
        else:
            out.append(f'<text class="t" x="{mx:.2f}" y="{Y(my) - 1.8:.2f}" text-anchor="middle">{escape(d.text)}</text>')
    # title block
    bx, by, bw, bh = w - 7 - 140, h - 7 - 26, 140, 26
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="white" stroke="#111" stroke-width=".5"/>')
    out.append(f'<line x1="{bx}" y1="{by + 13}" x2="{bx + bw}" y2="{by + 13}" stroke="#111" stroke-width=".3"/>')
    out.append(f'<text class="big" x="{bx + 3}" y="{by + 9}">{escape(sheet.title)}</text>')
    sc = f"{sheet.scale[0]}:{sheet.scale[1]}"
    out.append(f'<text class="t" x="{bx + 3}" y="{by + 20}">Scale {sc}   Sheet {sheet.size}   Units mm   '
               f'{datetime.date.today().isoformat()}{("   " + escape(author)) if author else ""}</text>')
    out.append(f'<text class="t" x="{bx + 3}" y="{by + 24.5}">Third angle projection - Fission360</text></svg>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


# ---------------------------------------------------------------------------- DXF
def write_dxf(sheet: Sheet, path: str):
    """DXF with VISIBLE / HIDDEN / DIMENSIONS layers, in sheet millimetres."""
    s = sheet.scale[0] / sheet.scale[1]
    o = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LTYPE", "70", "2",
         "0", "LTYPE", "2", "CONTINUOUS", "70", "0", "3", "Solid line", "72", "65", "73", "0", "40", "0.0",
         "0", "LTYPE", "2", "DASHED", "70", "0", "3", "Dashed", "72", "65", "73", "2", "40", "4.5", "49", "3.0", "49", "-1.5",
         "0", "ENDTAB",
         "0", "TABLE", "2", "LAYER", "70", "5",
         "0", "LAYER", "2", "CENTER", "70", "0", "62", "1", "6", "DASHED",
         "0", "LAYER", "2", "HATCH", "70", "0", "62", "9", "6", "CONTINUOUS",
         "0", "LAYER", "2", "VISIBLE", "70", "0", "62", "7", "6", "CONTINUOUS",
         "0", "LAYER", "2", "HIDDEN", "70", "0", "62", "8", "6", "DASHED",
         "0", "LAYER", "2", "DIMENSIONS", "70", "0", "62", "3", "6", "CONTINUOUS",
         "0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    def pl(points, layer):
        o.extend(["0", "POLYLINE", "8", layer, "66", "1", "70", "0"])
        for x, y in points:
            o.extend(["0", "VERTEX", "8", layer, "10", f"{x:.5f}", "20", f"{y:.5f}", "30", "0.0"])
        o.extend(["0", "SEQEND", "8", layer])

    for view, ox, oy in sheet.placed:
        for p in view.hidden:
            pl([(x * s + ox, y * s + oy) for x, y in p], "HIDDEN")
        for p in view.visible:
            pl([(x * s + ox, y * s + oy) for x, y in p], "VISIBLE")
        for p in view.marks:
            pl([(x * s + ox, y * s + oy) for x, y in p], "CENTER")
        for hl in hatch_lines(view.hatch, 3.0 / s):
            pl([(x * s + ox, y * s + oy) for x, y in hl], "HATCH")
        for text, anchor, label in view.notes:
            pl([(anchor[0] * s + ox, anchor[1] * s + oy), (label[0] * s + ox, label[1] * s + oy)], "DIMENSIONS")
            o.extend(["0", "TEXT", "8", "DIMENSIONS", "10", f"{label[0] * s + ox + 0.8:.4f}", "20", f"{label[1] * s + oy:.4f}",
                      "30", "0.0", "40", "3.2", "1", text.replace("\u00d8", "%%c")])
    for d in sheet.dims:
        pl([d.a, d.b], "DIMENSIONS")
        mx, my = (d.a[0] + d.b[0]) / 2, (d.a[1] + d.b[1]) / 2
        o.extend(["0", "TEXT", "8", "DIMENSIONS", "10", f"{mx:.4f}", "20", f"{my + 1:.4f}", "30", "0.0",
                  "40", "3.2", "1", d.text, "50", "90" if d.vertical else "0"])
    o.extend(["0", "ENDSEC", "0", "EOF"])
    with open(path, "w", encoding="latin-1") as fh:
        fh.write("\n".join(o) + "\n")


def export_drawing(shape, path: str, name="Part", views=("front", "top", "right"), size="A3", hidden=True):
    """Write a drawing sheet; the extension picks the format (.svg or .dxf)."""
    sheet = make_sheet(shape, name, views, size, hidden)
    if path.lower().endswith(".dxf"):
        write_dxf(sheet, path)
    else:
        write_svg(sheet, path)
    return sheet
