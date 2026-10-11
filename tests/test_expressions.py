import math

import pytest

from kerfline.core.expressions import ExpressionError, evaluate, to_angle, to_length
from kerfline.core.parameters import ParameterTable


def test_units_and_math():
    assert to_length(evaluate("1 in + 2mm")) == pytest.approx(27.4)
    assert to_angle(evaluate("90")) == pytest.approx(math.pi / 2)
    assert to_length(evaluate("sqrt(9 mm * 4 mm)")) == pytest.approx(6)
    assert to_length(evaluate("10 mm * sin(30 deg)")) == pytest.approx(5)


def test_rejects_code():
    for bad in ("__import__('os')", "open('x')", "a.b", "[1]", "'s'"):
        with pytest.raises(ExpressionError):
            evaluate(bad)


def test_parameter_dependencies_and_cycles():
    t = ParameterTable()
    t.add("80 mm", name="width")
    d = t.add("width / 2")
    assert t.value(d) == pytest.approx(40)
    t.set_expr("width", "100")
    assert t.value(d) == pytest.approx(50)
    with pytest.raises(ExpressionError):
        t.set_expr("width", d)  # cycle
    assert t.value("width") == pytest.approx(100)
    t.rename("width", "w")
    assert t.params[d].expr == "w / 2"
