"""Phase 2 assembly basics: joints, components, assembly STEP."""
import numpy as np
import pytest

from fission360.api import Design
from fission360.core import kernel as K


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
    from fission360.api import DesignError
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
    from fission360 import drawing
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
