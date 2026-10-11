"""Sheet-metal flanges and flat patterns."""
import math

import numpy as np
import pytest

from fission360.api import Design, DesignError
from fission360.core import kernel as K


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
