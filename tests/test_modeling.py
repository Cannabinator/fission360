import pytest

from kerfline.core import kernel as K
from kerfline.core import references as R
from kerfline.core.document import Document
from kerfline.core.features import default_data
from kerfline.sketch.model import Sketch


def make_block(doc, w="40 mm", h="20 mm"):
    f = doc.add_feature("sketch", {"plane": "XY"})
    s = f.sketch
    L = [s.add_line((0, 0), (40, 0)), s.add_line((40, 0), (40, 30)), s.add_line((40, 30), (0, 30)),
         s.add_line((0, 30), (0, 0))]
    E = s.entities
    for i in range(4):
        s.add_constraint("coincident", [E[L[i]].pts[1], E[L[(i + 1) % 4]].pts[0]])
    s.add_constraint("horizontal", [L[0]])
    s.add_constraint("horizontal", [L[2]])
    s.add_constraint("vertical", [L[1]])
    s.add_constraint("vertical", [L[3]])
    s.add_constraint("coincident", [E[L[0]].pts[0], 0])
    s.add_constraint("distance", [L[0]], param=doc.params.add(w, owner=f.id))
    s.add_constraint("distance", [L[1]], param=doc.params.add("30 mm", owner=f.id))
    doc.rebuild()
    d = default_data("extrude")
    d["profiles"] = [{"sketch": f.id, "uv": [5, 5]}]
    ex = doc.add_feature("extrude", d, numeric={"distance": (h, "length"), "taper": ("0", "angle")})
    return f, ex


def body(doc):
    return next(iter(doc.state.bodies.values()))


def vol(doc):
    return K.mass_properties(body(doc).shape)["volume_mm3"]


def test_extrude_and_parametric_update():
    doc = Document()
    doc.params.add("40 mm", name="width")
    sk, ex = make_block(doc, "width")
    assert vol(doc) == pytest.approx(40 * 30 * 20)
    doc.set_param("width", "60 mm")
    assert vol(doc) == pytest.approx(60 * 30 * 20)
    assert all(f.error is None for f in doc.features)


def test_fillet_shell_survive_param_change():
    doc = Document()
    doc.params.add("40 mm", name="width")
    make_block(doc, "width")
    b = body(doc)
    top = [f for f in K.faces(b.shape) if K.face_info(f)["normal"][2] > 0.99][0]
    doc.add_feature("fillet", {"edges": [R.edge_ref(b.id, e) for e in K.edges(top)]}, numeric={"radius": ("3", "length")})
    bottom = [f for f in K.faces(body(doc).shape) if K.face_info(f)["normal"][2] < -0.99][0]
    doc.add_feature("shell", {"faces": [R.face_ref(b.id, bottom)], "side": "inside"},
                    numeric={"thickness": ("2", "length")})
    v0 = vol(doc)
    doc.set_param("width", "80 mm")
    assert all(f.error is None for f in doc.features), [(f.name, f.error) for f in doc.features]
    assert vol(doc) > v0
    assert K.is_valid(body(doc).shape)


def test_cut_hole_revolve_mirror_pattern():
    doc = Document()
    sk, ex = make_block(doc)
    v = vol(doc)
    # sketch on the top face with a point -> hole
    top = [f for f in K.faces(body(doc).shape) if K.face_info(f)["normal"][2] > 0.99][0]
    s2 = doc.add_feature("sketch", {"plane": {"face": R.face_ref(body(doc).id, top)}})
    pid = s2.sketch.add_point(10, 10)
    doc.rebuild()
    doc.add_feature("hole", {"points": [{"sketch": s2.id, "point": pid}], "hole_type": "counterbore"},
                    numeric={"diameter": ("5", "length"), "depth": ("10", "length"),
                             "cbore_diameter": ("9", "length"), "cbore_depth": ("3", "length"),
                             "tip_angle": ("118", "angle")})
    assert doc.features[-1].error is None
    assert vol(doc) < v
    # mirror across YZ joined -> body doubles
    v2 = vol(doc)
    doc.add_feature("mirror", {"bodies": [body(doc).id], "plane": "YZ", "combine": False})
    assert len(doc.state.bodies) == 2
    doc.add_feature("pattern_rect", {"bodies": [body(doc).id], "axis1": "X", "axis2": "Y", "combine": False},
                    numeric={"count1": ("3", "scalar"), "spacing1": ("100", "length"), "count2": ("1", "scalar"),
                             "spacing2": ("0", "length")})
    assert len(doc.state.bodies) == 4
    assert v2 > 0


def test_revolve_primitives_combine_split():
    doc = Document()
    f = doc.add_feature("sketch", {"plane": "XZ"})
    s = f.sketch
    pts = [(5, 0), (15, 0), (15, 10), (5, 10)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        s.add_line(a, b)
    doc.rebuild()
    d = default_data("revolve")
    d.update(profiles=[{"sketch": f.id, "uv": [10, 5]}], axis="Z")
    doc.add_feature("revolve", d, numeric={"angle": ("360 deg", "angle")})
    assert doc.features[-1].error is None
    import math
    assert vol(doc) == pytest.approx(math.pi * (15 ** 2 - 5 ** 2) * 10, rel=1e-4)
    doc.add_feature("box", {"plane": "XY", "operation": "new"},
                    numeric={k: (v, "length") for k, v in dict(x="0", y="0", length="30", width="30", height="30").items()})
    ids = list(doc.state.bodies)
    doc.add_feature("combine", {"target": ids[0], "tools": [ids[1]], "operation": "cut"})
    assert len(doc.state.bodies) == 1 and doc.features[-1].error is None
    doc.add_feature("split_body", {"body": list(doc.state.bodies)[0], "plane": "YZ"})
    assert len(doc.state.bodies) == 2


def test_undo_redo_save_load(tmp_path):
    doc = Document()
    with doc.transaction("block"):
        make_block(doc)
    with doc.transaction("box"):
        doc.add_feature("box", {"plane": "XY", "operation": "join"},
                        numeric={k: (v, "length") for k, v in dict(x="0", y="0", length="10", width="10", height="50").items()})
    v_after = vol(doc)
    doc.undo()
    assert vol(doc) == pytest.approx(40 * 30 * 20)
    doc.redo()
    assert vol(doc) == pytest.approx(v_after)
    p = tmp_path / "t.f3x"
    doc.save(str(p))
    d2 = Document.load(str(p))
    assert vol(d2) == pytest.approx(v_after)


def test_suppress_and_marker():
    doc = Document()
    sk, ex = make_block(doc)
    doc.set_suppressed(ex.id, True)
    assert not doc.state.bodies
    doc.set_suppressed(ex.id, False)
    doc.set_marker(1)
    assert not doc.state.bodies and sk.id in doc.state.sketches
    doc.set_marker(2)
    assert doc.state.bodies


def test_export_formats(tmp_path):
    doc = Document()
    make_block(doc)
    for ext in ("step", "stl", "iges", "obj", "brep"):
        p = tmp_path / f"o.{ext}"
        doc.export_bodies(str(p))
        assert p.stat().st_size > 100
    assert K.import_step(str(tmp_path / "o.step"))
