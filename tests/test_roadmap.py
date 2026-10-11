"""Phase 0/1 roadmap features: diagnostics, text, sketch ops, 2D exchange, threads, rib, API, versions."""
import json
import math
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from kerfline.api import Design
from kerfline.core import kernel as K
from kerfline.core import references as R
from kerfline.core.document import Document
from kerfline.core.features import default_data
from kerfline.sketch import ops
from kerfline.sketch.model import Sketch

XY = K.ORIGIN_FRAMES["XY"]


def block():
    return K.box(XY, 0, 0, 40, 30, 20)


# ---------------------------------------------------------------- Phase 0: robustness layer
def test_fillet_failure_names_largest_radius():
    b = block()
    vert = [e for e in K.edges(b) if abs(K.edge_info(e)["tangent"][2]) > 0.99]
    with pytest.raises(K.KernelError, match="largest radius that works is about"):
        K.fillet(b, vert, 50)


def test_chamfer_and_shell_diagnostics():
    b = block()
    vert = [e for e in K.edges(b) if abs(K.edge_info(e)["tangent"][2]) > 0.99]
    with pytest.raises(K.KernelError, match="largest distance"):
        K.chamfer(b, vert, 40)
    top = [f for f in K.faces(b) if K.face_info(f)["normal"][2] > 0.99][0]
    with pytest.raises(K.KernelError):
        K.shell(b, [top], 25)


def test_variable_radius_fillet():
    b = block()
    e = [x for x in K.edges(b) if abs(K.edge_info(x)["tangent"][2]) > 0.99][:1]
    r = K.fillet(b, e, 1, 6)
    assert K.is_valid(r) and K.mass_properties(r)["volume_mm3"] < K.mass_properties(b)["volume_mm3"]


def test_coplanar_touching_boolean_works():
    # glyph-shaped prisms sitting on a face must join (regression for the retry layer)
    t = K.text_in_frame("A", 8, K.Frame([0, 0, 20], [1, 0, 0], [0, 0, 1]), (5, 5))
    tool = K.prism(K.faces(t)[0], (0, 0, 1))
    assert K.is_valid(K.fuse(block(), tool))


def test_lost_reference_is_flagged():
    doc = Document()
    sk = doc.add_feature("sketch", {"plane": "XY"})
    sk.sketch.add_circle((0, 0), 5)
    doc.rebuild()
    d = default_data("extrude")
    d["profiles"] = [{"sketch": "f_missing", "uv": [0, 0]}]
    f = doc.add_feature("extrude", d, numeric={"distance": ("5", "length"), "taper": ("0", "angle")})
    assert f.error and f.error_kind == "reference"


def test_text_diffable_save_roundtrip(tmp_path):
    doc = Document()
    f = doc.add_feature("sketch", {"plane": "XY"})
    f.sketch.add_text((1, 2), "Hi", 6, bold=True, angle=0.5)
    doc.rebuild()
    p = tmp_path / "t.f3x"
    doc.save(str(p))
    raw = p.read_text()
    assert raw.startswith("{") and "\n" in raw and json.loads(raw)["format"] == "kerfline"  # plain, diffable
    t = [e for e in Document.load(str(p)).features[0].sketch.entities.values() if e.kind == "text"][0]
    assert (t.text, t.height, t.bold, round(t.angle, 3)) == ("Hi", 6, True, 0.5)
    doc.save(str(p), compress=True)
    assert Document.load(str(p)).features  # gzip still loads


# ---------------------------------------------------------------- Phase 1: sketch
def test_text_has_letter_holes():
    s = Sketch()
    s.add_text((0, 0), "O", 10)
    prof = K.build_profiles(s, XY)
    assert len(prof) == 2  # ring + counter, like Fusion's profile regions


def test_ellipse_profile_area():
    s = Sketch()
    s.add_ellipse((0, 0), (10, 0), 4)
    (p,) = K.build_profiles(s, XY)
    assert K.area(p) == pytest.approx(math.pi * 10 * 4, rel=1e-3)


def rect(s, x=0, y=0, w=40, h=20):
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    L = [s.add_line(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    ops.join_coincident(s, L)
    return L


def test_offset_mirror_pattern_extend():
    s = Sketch()
    L = rect(s)
    off = ops.offset_curves(s, L, -3, XY)
    assert len(off) == 4
    inner = K.build_profiles(s, XY)
    assert sorted(round(K.area(p)) for p in inner) == sorted([34 * 14, 800 - 34 * 14])
    ax = s.add_line((60, -5), (60, 30))
    m = ops.mirror_curves(s, L, ax)
    assert len(m) == 4 and s.xy(s.entities[m[0]].pts[0])[0] == pytest.approx(120)
    n0 = len(s.curves())
    assert len(ops.pattern_rect(s, [L[0]], 3, 0, 2, 10)) == 5
    assert len(ops.pattern_circ(s, [L[1]], (0, 0), 4)) == 3
    assert len(s.curves()) == n0 + 8
    s2 = Sketch()
    ln = s2.add_line((0, 0), (10, 0))
    s2.add_line((20, -5), (20, 5))
    assert ops.extend_line(s2, ln, s2.entities[ln].pts[1])
    assert s2.xy(s2.entities[ln].pts[1]) == pytest.approx((20, 0))


def test_dxf_roundtrip_and_svg_import(tmp_path):
    s = Sketch()
    rect(s)
    s.add_circle((20, 10), 4)
    s.add_arc((0, 0), (5, 0), (0, 5))
    p = tmp_path / "a.dxf"
    ops.write_dxf(s, str(p))
    s2 = Sketch()
    ids = ops.import_2d_file(s2, str(p))
    assert len(ids) == len(s.curves(False))
    assert any(e.kind == "circle" and e.r == pytest.approx(4) for e in s2.curves())
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50">'
                   '<rect x="5" y="5" width="30" height="20"/><circle cx="60" cy="25" r="10"/>'
                   '<path d="M70 5 C 80 5 90 15 90 25 L 70 25 Z"/></svg>')
    s3 = Sketch()
    ops.import_2d_file(s3, str(svg))
    assert any(e.kind == "circle" and e.r == pytest.approx(10) for e in s3.curves())
    assert len(K.build_profiles(s3, XY)) >= 3


# ---------------------------------------------------------------- Phase 1: features, io
def make_plate():
    d = Design()
    sk = d.sketch("XY")
    sk.rect(0, 0, 60, 40)
    b = d.extrude(sk.profile(5, 5), "12 mm")
    return d, b


def test_api_selectors_and_parametric_edit():
    d, b = make_plate()
    d.param("w", "60 mm")
    d.fillet(d.bodies[0].edges(direction=(0, 0, 1)), "3 mm")
    v0 = d.bodies[0].volume
    d.hole(d.bodies[0].face(normal=(0, 0, 1)), at=(30, 20), diameter="6 mm", depth="8 mm")
    assert d.bodies[0].volume < v0
    assert all(f.error is None for f in d.doc.features)
    assert d.value("w") == 60


def test_tapped_hole_and_cosmetic_thread():
    d, b = make_plate()
    d.hole(b.face(normal=(0, 0, 1)), at=(30, 20), thread="M6x1", depth="10 mm")
    notes = d.doc.state.annotations
    assert notes and notes[0]["text"].startswith("M6x1")
    v = d.bodies[0].volume
    cyl = d.bodies[0].faces(type="cylinder")
    d.thread(cyl, "M6x1")
    assert d.bodies[0].volume == pytest.approx(v)  # cosmetic: no geometry change
    assert len(d.doc.state.annotations) == 2


def test_rib_web():
    d, b = make_plate()
    sk = d.sketch("XZ")
    sk.line((5, 12), (55, 12))
    d.rib(sk.curves(), "3 mm", "10 mm")
    assert d.doc.features[-1].error is None
    assert len(d.doc.state.bodies) == 1
    assert d.bodies[0].volume > 60 * 40 * 12


def test_text_emboss_via_auto_extrude():
    d, b = make_plate()
    top = b.face(normal=(0, 0, 1))
    sk = d.sketch(top)
    sk.text(5, 10, "AB", 10)
    profs = sk.profiles()
    v = d.bodies[0].volume
    d.extrude(profs[:2], "1 mm")  # glyph regions; operation chosen automatically
    assert d.doc.features[-1].error is None
    assert d.bodies[0].volume > v


def test_3mf_export(tmp_path):
    d, b = make_plate()
    p = tmp_path / "x.3mf"
    d.export(str(p))
    z = zipfile.ZipFile(p)
    model = z.read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in model and "<triangle" in model


def test_versions_diff_and_restore():
    d, b = make_plate()
    d.param("w", "60 mm")
    d.doc.save_version("one")
    d.param("w", "90 mm")
    sk = d.sketch("XY")
    diff = Document.diff(d.doc.versions[0]["data"], d.doc.to_dict())
    assert any("parameter w" in x for x in diff) and any("added" in x for x in diff)
    n = len(d.doc.features)
    d.doc.restore_version(0)
    assert len(d.doc.features) == n - 1 and d.value("w") == 60
    d.doc.undo()
    assert len(d.doc.features) == n


def test_headless_run(tmp_path):
    script = tmp_path / "s.py"
    script.write_text('sk = design.sketch("XY"); sk.rect(0, 0, 20, 20)\n'
                      'design.extrude(sk.profile(5, 5), "5 mm")\n')
    out = tmp_path / "o.f3x"
    r = subprocess.run([sys.executable, "-m", "kerfline", "--run", str(script), "--out", str(out)],
                       capture_output=True, text=True, env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin",
                                                          "PYTHONPATH": str(__import__("pathlib").Path(__file__).parents[1])})
    assert r.returncode == 0, r.stderr
    assert Document.load(str(out)).state.bodies
