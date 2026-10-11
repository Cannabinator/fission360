"""Sheet-metal flanges and flat patterns."""
import math

import numpy as np
import pytest

from kerfline.api import Design, DesignError
from kerfline.core import kernel as K


def plate(d, w=60, l=40, t=2):
    return d.box(0, 0, w, l, t)


def side_face(sel, normal):
    return sel.faces(normal=normal)[0]


def test_90_degree_flange_geometry_and_volume():
    d = Design()
    p = plate(d)
    v0 = K.mass_properties(p.shape)["volume_mm3"]
    d.flange(side_face(p, (0, 1, 0)), height="15 mm", angle="90 deg", radius="3 mm")
    s = d.bodies[0].shape
    lo, hi = K.bbox(s)
    # wall rises to R + t + height above the plate bottom, extends R + t beyond the edge
    assert hi[2] == pytest.approx(2 + 3 + 15, abs=1e-3)
    assert hi[1] == pytest.approx(40 + 3 + 2, abs=1e-3)
    vol = K.mass_properties(s)["volume_mm3"]
    bend = (math.pi / 2) * ((5 ** 2 - 3 ** 2) / 2) * 60          # annular sector, 60 mm wide
    assert vol == pytest.approx(v0 + bend + 60 * 2 * 15, rel=1e-3)
    assert len(K.solids(s)) == 1


def test_flange_other_direction_and_angle():
    d = Design()
    p = plate(d)
    d.flange(side_face(p, (1, 0, 0)), height="10 mm", angle="45 deg", radius="2 mm", flip=True)
    lo, hi = K.bbox(d.bodies[0].shape)
    assert lo[2] < 0 and len(K.solids(d.bodies[0].shape)) == 1       # bent downward


def test_flat_pattern_dimensions(tmp_path):
    d = Design()
    p = plate(d, 60, 40, 2)
    d.flange(side_face(p, (0, 1, 0)), height="15 mm", angle="90 deg", radius="3 mm", k_factor="0.44")
    size = d.flat_pattern(str(tmp_path / "flat.dxf"))
    ba = (math.pi / 2) * (3 + 0.44 * 2)
    assert sorted(size) == pytest.approx(sorted([60.0, 40 + ba + 15]), abs=1e-3)
    txt = (tmp_path / "flat.dxf").read_text()
    assert "BEND" in txt and "CUT" in txt


def test_two_flanges_and_holes_in_flat_pattern(tmp_path):
    d = Design()
    p = plate(d, 60, 40, 2)
    d.hole(p.faces(normal=(0, 0, 1))[0], at=(30, 20), diameter="8 mm", depth="2 mm")
    d.flange(side_face(d.bodies[0], (0, 1, 0)), height="10 mm", radius="2 mm")
    d.flange(side_face(d.bodies[0], (0, -1, 0)), height="10 mm", radius="2 mm")
    size = d.flat_pattern(str(tmp_path / "f.dxf"))
    ba = (math.pi / 2) * (2 + 0.44 * 2)
    assert sorted(size) == pytest.approx(sorted([60.0, 40 + 2 * (ba + 10)]), abs=1e-3)
    assert (tmp_path / 'f.dxf').read_text().count('VERTEX') > 40       # the 8 mm hole is part of the cut outline
    assert len(d.doc.state.sheet) == 2


def test_flat_pattern_without_bends_is_an_error(tmp_path):
    d = Design()
    plate(d)
    with pytest.raises(Exception, match="no bends"):
        d.flat_pattern(str(tmp_path / "x.dxf"))


def test_bad_flange_reports_error():
    d = Design()
    p = plate(d)
    with pytest.raises(DesignError):
        d.flange(p.faces(normal=(0, 0, 1))[0], height="5 mm", angle="200 deg")


def test_flange_on_flange_chain_and_flat_pattern(tmp_path):
    d = Design()
    p = plate(d, 60, 40, 2)
    d.flange(side_face(p, (0, 1, 0)), height="15 mm", angle="90 deg", radius="3 mm")
    # the tip of the wall: top face of the flange (normal +Z)
    tip = d.bodies[0].faces(normal=(0, 0, 1))
    tip = [f for f in tip if f["face"]["sig"]["center"][2] > 10][0]
    d.flange(tip, height="10 mm", angle="90 deg", radius="2 mm", flip=False)
    sheet = d.doc.state.sheet
    assert [b["parent"] for b in sheet] == [None, 0]
    assert len(K.solids(d.bodies[0].shape)) == 1
    size = d.flat_pattern(str(tmp_path / "c.dxf"))
    ba1, ba2 = (math.pi / 2) * (3 + 0.44 * 2), (math.pi / 2) * (2 + 0.44 * 2)
    assert sorted(size) == pytest.approx(sorted([60.0, 40 + ba1 + 15 + ba2 + 10]), abs=1e-3)
    assert (tmp_path / "c.dxf").read_text().count("BEND") >= 3          # layer table + two bend lines


def test_corner_relief_gaps_trim_flange_and_flat_pattern(tmp_path):
    d = Design()
    p = plate(d, 60, 40, 2)
    d.flange(side_face(p, (0, 1, 0)), height="10 mm", radius="2 mm", gap_start="4 mm", gap_end="6 mm")
    b = d.doc.state.sheet[0]
    assert b["length"] == pytest.approx(50)
    lo, hi = K.bbox(d.bodies[0].shape)
    # the wall spans x = 4 .. 54 only; the plate itself still spans 0 .. 60
    wall_x = [K.face_info(f)["center"][0] for f in K.faces(d.bodies[0].shape)
              if K.face_info(f)["type"] == "plane" and K.face_info(f)["center"][2] > 6]
    assert min(wall_x) > 3.9 and max(wall_x) < 54.1
    assert len(K.solids(d.bodies[0].shape)) == 1
    d.flat_pattern(str(tmp_path / "r.dxf"))
    txt = (tmp_path / "r.dxf").read_text()
    assert "BEND" in txt


def test_adjacent_flanges_with_reliefs_do_not_overlap():
    d = Design()
    p = plate(d, 60, 40, 2)
    t = 2
    r = 2
    d.flange(side_face(p, (0, 1, 0)), height="10 mm", radius=f"{r} mm", gap_start=f"{t + r} mm")
    d.flange(side_face(d.bodies[0], (1, 0, 0)), height="10 mm", radius=f"{r} mm", gap_end=f"{t + r} mm")
    assert len(K.solids(d.bodies[0].shape)) == 1 and len(d.doc.state.sheet) == 2


def test_hem_folds_edge_back(tmp_path):
    d = Design()
    p = plate(d, 60, 40, 2)
    v0 = K.mass_properties(p.shape)["volume_mm3"]
    d.hem(side_face(p, (0, 1, 0)), length="10 mm", gap="2 mm")      # R = 1 mm
    s = d.bodies[0].shape
    lo, hi = K.bbox(s)
    assert hi[2] == pytest.approx(2 + 2 * 1 + 2, abs=1e-3)           # plate t + gap + leg t above the bottom
    assert len(K.solids(s)) == 1
    vol = K.mass_properties(s)["volume_mm3"]
    bend = math.pi * ((3 ** 2 - 1 ** 2) / 2) * 60
    assert vol == pytest.approx(v0 + bend + 60 * 2 * 10, rel=1e-3)
    size = d.flat_pattern(str(tmp_path / "h.dxf"))
    assert sorted(size) == pytest.approx(sorted([60.0, 40 + math.pi * (1 + 0.44 * 2) + 10]), abs=1e-3)


def test_zero_radius_hem_is_rejected():
    d = Design()
    p = plate(d)
    with pytest.raises(DesignError, match="radius"):
        d.hem(side_face(p, (0, 1, 0)), gap="0 mm")
