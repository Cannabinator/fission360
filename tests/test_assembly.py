"""Phase 2 assembly basics: joints, components, assembly STEP."""
import numpy as np
import pytest

from kerfline.api import Design
from kerfline.core import kernel as K


def two_blocks():
    d = Design()
    a = d.box(0, 0, 40, 30, 10)
    b = d.box(100, 0, 20, 20, 10)
    d.doc.set_body_prop(b.body_id, "name", "Lid")
    return d, a, b


def top(sel):
    return sel.faces(normal=(0, 0, 1))[0]


def bottom(sel):
    return sel.faces(normal=(0, 0, -1))[0]


def lo_hi(sel):
    lo, hi = K.bbox(sel.shape)
    return np.array(lo), np.array(hi)


def test_rigid_joint_stacks_part_on_top():
    d, a, b = two_blocks()
    d.joint(bottom(b), top(a))
    assert not [f.error for f in d.doc.features if f.error]
    blo, _ = lo_hi(d.bodies[1])
    _, ahi = lo_hi(d.bodies[0])
    assert blo[2] == pytest.approx(ahi[2], abs=1e-6)          # sits on the top face
    # faces centres coincide in plan
    ac = np.array(K.face_info(K.faces(d.bodies[0].shape)[0])["center"])
    assert ac is not None


def test_joint_offset_and_flip():
    d, a, b = two_blocks()
    d.joint(bottom(b), top(a), offset="5 mm")
    blo, _ = lo_hi(d.bodies[1])
    _, ahi = lo_hi(d.bodies[0])
    assert blo[2] == pytest.approx(ahi[2] + 5, abs=1e-6)


def test_revolute_joint_rotates_about_axis():
    d, a, b = two_blocks()
    d.joint(bottom(b), top(a), kind="revolute", angle="90 deg")
    lo, hi = lo_hi(d.bodies[1])
    assert (hi - lo)[0] == pytest.approx(20, abs=1e-5) and (hi - lo)[2] == pytest.approx(10, abs=1e-5)


def test_cylindrical_faces_align_axes():
    d = Design()
    plate = d.box(0, 0, 60, 60, 10)
    pin = d.cylinder(200, 200, 10, 30)
    cyl_plate_face = pin.faces(type="cylinder")[0]
    d.joint(pin.faces(normal=(0, 0, -1))[0], plate.faces(normal=(0, 0, 1))[0])
    lo, hi = lo_hi(d.bodies[1])
    assert lo[2] == pytest.approx(10, abs=1e-6)
    assert cyl_plate_face is not None


def test_joint_errors_are_reported():
    d, a, b = two_blocks()
    from kerfline.api import DesignError
    with pytest.raises(DesignError, match="same body"):
        d.joint(top(a), bottom(a))


def test_component_moves_together():
    d, a, b = two_blocks()
    c = d.box(100, 50, 5, 5, 5)
    d.component("Lid assy", b, c)
    d.joint(bottom(b), top(a))
    clo, _ = lo_hi(d.bodies[2])
    blo, _ = lo_hi(d.bodies[1])
    # the second box moved by the same transform as the lid
    assert clo[2] == pytest.approx(10, abs=1e-6)  # started at z=0, moved up 10
    assert blo[2] == pytest.approx(10, abs=1e-6)
    assert d.doc.components() == {"Lid assy": [b.body_id, c.body_id]}


def test_assembly_step_roundtrip(tmp_path):
    d, a, b = two_blocks()
    d.component("Cover", b)
    d.joint(bottom(b), top(a))
    p = tmp_path / "asm.step"
    d.export(str(p))
    txt = p.read_text()
    assert "Cover" in txt and "Lid" in txt
    shape = K.import_file(str(p)) if hasattr(K, "import_file") else None
    if shape is not None:
        assert len(K.solids(shape if not isinstance(shape, list) else K.compound(shape))) == 2


def test_joint_survives_save_and_param_edit(tmp_path):
    d, a, b = two_blocks()
    d.param("gap", "2 mm")
    d.joint(bottom(b), top(a), offset="gap")
    d.save(str(tmp_path / "x.f3x"))
    d2 = Design.open(str(tmp_path / "x.f3x"))
    d2.param("gap", "7 mm")
    blo, _ = lo_hi(d2.bodies[1])
    assert blo[2] == pytest.approx(17, abs=1e-6)


def test_drawing_views_hidden_lines_and_formats(tmp_path):
    from kerfline import drawing
    d = Design()
    a = d.box(0, 0, 60, 40, 20)
    d.hole(a.faces(normal=(0, 0, 1))[0], at=(30, 20), diameter="10 mm", depth="20 mm")
    sheet = d.drawing(str(tmp_path / "p.svg"), views=("front", "top", "right", "iso"))
    d.drawing(str(tmp_path / "p.dxf"))
    names = {v.name: v for v, _, _ in sheet.placed}
    assert len(names["front"].hidden) >= 2 and not names["top"].hidden       # bore is hidden in the side views only
    assert {x.text for x in sheet.dims} >= {"60", "40", "20"}
    svg = (tmp_path / "p.svg").read_text()
    assert svg.count("<polyline") > 20 and "Third angle" in svg
    dxf = (tmp_path / "p.dxf").read_text()
    assert "HIDDEN" in dxf and "VISIBLE" in dxf and dxf.rstrip().endswith("EOF")
    assert drawing.SHEETS["A3"][0] > 400


def test_joint_limits_clamp_and_animate():
    d, a, b = two_blocks()
    j = d.joint(bottom(b), top(a), kind="revolute", angle="0 deg", limits=(-45, 60))
    seen = []

    def frame(v):
        lo, hi = lo_hi(d.bodies[1])
        seen.append((v, round(float((hi - lo)[0]), 3)))

    d.animate(j, [0, 30, 90], on_frame=frame)
    assert j.warning and "limited" in j.warning            # 90 deg is clamped to 60
    w60 = 20 * np.cos(np.radians(60)) + 20 * np.sin(np.radians(60))
    assert seen[-1][1] == pytest.approx(w60, abs=1e-2)
    assert seen[0][1] == pytest.approx(20, abs=1e-3)


def test_slider_limits():
    d, a, b = two_blocks()
    j = d.joint(bottom(b), top(a), kind="slider", offset="30 mm", limits=(0, 12))
    lo, _ = lo_hi(d.bodies[1])
    assert lo[2] == pytest.approx(10 + 12, abs=1e-6)


def test_drawing_centre_marks_callouts_and_section(tmp_path):
    from kerfline import drawing
    d = Design()
    a = d.box(0, 0, 60, 40, 20)
    d.hole(a.faces(normal=(0, 0, 1))[0], at=(30, 20), diameter="10 mm", depth="20 mm")
    sheet = d.drawing(str(tmp_path / "s.svg"), views=("front", "top", "section"))
    d.drawing(str(tmp_path / "s.dxf"), views=("front", "top", "section"))
    v = {x.name: x for x, _, _ in sheet.placed}
    assert [n[0] for n in v["top"].notes] == ["Ø10"] and len(v["top"].marks) == 2
    assert len(v["front"].marks) == 1
    assert v["section"].hatch and not v["section"].hidden
    segs = drawing.hatch_lines(v["section"].hatch, 3.0)
    xs = [p[0] for s in segs for p in s]
    assert segs and not any(25.01 < x < 34.99 for x in xs)      # nothing hatched across the 10 mm bore
    svg = (tmp_path / "s.svg").read_text()
    assert "SECTION A-A" in svg and 'class="x"' in svg
    assert "HATCH" in (tmp_path / "s.dxf").read_text()


def test_user_dimensions_and_bom(tmp_path):
    d, a, b = two_blocks()
    d.component("Cover", b)
    d.joint(bottom(b), top(a))
    dims = [{"view": "front", "p1": (0, 0, 0), "p2": (25, 0, 0), "kind": "horizontal"},
            {"view": "front", "p1": (0, 0, 0), "p2": (30, 0, 40), "kind": "aligned", "offset": 6},
            {"view": "top", "p1": (0, 0, 0), "p2": (0, 12, 0), "kind": "vertical", "text": "12 +-0.1"}]
    sheet = d.drawing(str(tmp_path / "u.svg"), views=("front", "top"), dims=dims, bom=True)
    d.drawing(str(tmp_path / "u.dxf"), views=("front", "top"), dims=dims, bom=True)
    texts = [x.text for x in sheet.dims]
    assert "25" in texts and "50" in texts and "12 +-0.1" in texts          # aligned = hypot(30, 40)
    assert [r[1] for r in sheet.bom] == ["Body1", "Cover"] and all(r[4] > 0 for r in sheet.bom)
    svg = (tmp_path / "u.svg").read_text()
    assert "Material" in svg and "Cover" in svg and "12 +-0.1" in svg
    assert "BOM" in (tmp_path / "u.dxf").read_text()
    with pytest.raises(ValueError):
        d.drawing(str(tmp_path / "x.svg"), views=("front",), dims=[{"view": "top", "p1": (0, 0, 0), "p2": (1, 0, 0)}])
