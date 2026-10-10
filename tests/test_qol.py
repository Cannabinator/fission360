"""Fusion-style QOL behaviour of the modelling core."""
import pytest

from fission360.core import kernel as K
from fission360.core import references as R
from fission360.core.document import Document, Feature
from fission360.core.features import default_data, execute


def box(doc, h="20"):
    doc.add_feature("box", {"plane": "XY", "operation": "new"},
                    numeric={k: (v, "length") for k, v in dict(x="0", y="0", length="40", width="30", height=h).items()})
    return next(iter(doc.state.bodies.values()))


def test_tangent_chain_follows_fillets():
    doc = Document()
    b = box(doc)
    vert = [e for e in K.edges(b.shape) if abs(K.edge_info(e)["tangent"][2]) > 0.99]
    doc.add_feature("fillet", {"edges": [R.edge_ref(b.id, e) for e in vert], "tangent_chain": False},
                    numeric={"radius": ("5", "length")})
    shape = doc.state.bodies[b.id].shape
    top = [f for f in K.faces(shape) if K.face_info(f)["normal"][2] > 0.99][0]
    one = [e for e in K.edges(top) if K.edge_info(e)["type"] == "line"][0]
    chain = K.tangent_chain(shape, [one])
    assert len(chain) == 8  # 4 lines + 4 arcs of the rounded rectangle loop


def test_fillet_face_selection_rounds_all_its_edges():
    doc = Document()
    b = box(doc)
    top = [f for f in K.faces(b.shape) if K.face_info(f)["normal"][2] > 0.99][0]
    f = doc.add_feature("fillet", {"edges": [{"face": R.face_ref(b.id, top)}]}, numeric={"radius": ("2", "length")})
    assert f.error is None
    assert len(K.faces(doc.state.bodies[b.id].shape)) == 6 + 4  # the 4 top edges are rounded


@pytest.mark.parametrize("dist,expected", [("-10", "cut"), ("10", "join")])
def test_auto_operation_from_face_sketch(dist, expected):
    doc = Document()
    b = box(doc)
    top = [f for f in K.faces(b.shape) if K.face_info(f)["normal"][2] > 0.99][0]
    s = doc.add_feature("sketch", {"plane": {"face": R.face_ref(b.id, top)}})
    s.sketch.add_circle((15, 15), 5)
    doc.rebuild()
    d = default_data("extrude")
    d.update(profiles=[{"sketch": s.id, "uv": [15, 15]}], operation="auto")
    f = Feature("fx", "extrude", "t", d, {"distance": doc.params.add(dist), "taper": doc.params.add("0", "angle")})
    st = doc.state.copy()
    execute(doc, f, st)
    assert f.resolved_operation == expected
    assert len(st.bodies) == 1


def test_auto_operation_free_space_is_new_body():
    doc = Document()
    box(doc)
    s = doc.add_feature("sketch", {"plane": "XY"})
    s.sketch.add_circle((100, 100), 5)
    doc.rebuild()
    d = default_data("extrude")
    d.update(profiles=[{"sketch": s.id, "uv": [100, 100]}], operation="auto")
    f = Feature("fx", "extrude", "t", d, {"distance": doc.params.add("10"), "taper": doc.params.add("0", "angle")})
    st = doc.state.copy()
    execute(doc, f, st)
    assert f.resolved_operation == "new" and len(st.bodies) == 2
