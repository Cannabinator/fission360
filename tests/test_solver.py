import pytest

from fission360.sketch.model import Sketch, SketchError


def rect(s):
    L = [s.add_line((0, 0), (40, 1)), s.add_line((40, 1), (41, 25)), s.add_line((41, 25), (1, 26)),
         s.add_line((1, 26), (0, 0))]
    E = s.entities
    for i in range(4):
        s.add_constraint("coincident", [E[L[i]].pts[1], E[L[(i + 1) % 4]].pts[0]])
    s.add_constraint("horizontal", [L[0]])
    s.add_constraint("horizontal", [L[2]])
    s.add_constraint("vertical", [L[1]])
    s.add_constraint("vertical", [L[3]])
    return L


def test_fully_constrained_rectangle():
    vals = {"a": 50.0, "b": 30.0}
    s = Sketch()
    s.param_value = vals.__getitem__
    L = rect(s)
    assert s.dof == 4
    s.add_constraint("coincident", [s.entities[L[0]].pts[0], 0])
    s.add_constraint("distance", [L[0]], param="a")
    s.add_constraint("distance", [L[1]], param="b")
    assert s.dof == 0
    assert s.xy(s.entities[L[2]].pts[0]) == pytest.approx((50, 30))
    vals["a"] = 80
    s.solve()
    assert s.xy(s.entities[L[2]].pts[0]) == pytest.approx((80, 30))


def test_redundant_constraint_rejected():
    s = Sketch()
    L = rect(s)
    with pytest.raises(SketchError):
        s.add_constraint("horizontal", [L[0]])


def test_tangent_and_drag():
    from fission360.sketch.solver import r_point_on_line
    s = Sketch()
    l = s.add_line((0, 0), (50, 0))
    c = s.add_circle((20, 10), 5)
    s.add_constraint("tangent", [l, c])

    def gap():
        e, ln = s.entities[c], s.entities[l]
        a, b = s.xy(ln.pts[0]), s.xy(ln.pts[1])
        return abs(r_point_on_line((*s.xy(e.pts[0]), *a, *b))) - e.r

    assert gap() == pytest.approx(0, abs=1e-7)
    s.solve(drag={s.entities[c].pts[0]: (25, 40)})
    assert gap() == pytest.approx(0, abs=1e-6)
    assert s.xy(s.entities[c].pts[0]) == pytest.approx((25, 40), abs=0.5)


def test_roundtrip():
    s = Sketch()
    rect(s)
    s2 = Sketch.from_dict(s.to_dict())
    assert s2.to_dict() == s.to_dict()
