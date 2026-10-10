"""Unit-aware expression engine for user parameters.

Every numeric input in Fission360 (dimensions, feature distances, angles,
pattern counts) is an *expression* string such as ``"width / 2 + 3 mm"`` or
``"30 deg"``.  Expressions are parsed with Python's ``ast`` module and
evaluated by a small whitelist interpreter -- no ``eval`` -- so documents
from untrusted sources cannot execute code.

Internally lengths are millimetres and angles are radians.  A bare number
takes the *expected* unit of the field it is typed into (mm for lengths,
degrees for angles), mirroring Fusion 360's behaviour.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Quantities
# --------------------------------------------------------------------------

LENGTH = (1, 0)
ANGLE = (0, 1)
SCALAR = (0, 0)

_LENGTH_UNITS = {
    "mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 1e-3, "in": 25.4, "inch": 25.4,
    "ft": 304.8, "yd": 914.4,
}
_ANGLE_UNITS = {"deg": math.pi / 180.0, "rad": 1.0, "grad": math.pi / 200.0}


class ExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Quantity:
    value: float  # in base units (mm / rad)
    dims: tuple[int, int] = SCALAR  # (length exponent, angle exponent)

    def _check_same(self, other: "Quantity", op: str) -> None:
        if self.dims != other.dims:
            # Allow mixing unitless scalars into additions: "10 mm + 2"
            # is treated as 10 mm + 2 mm by the caller's coercion step.
            raise ExpressionError(f"incompatible units in '{op}'")

    def __add__(self, o):
        o = _coerce_like(o, self)
        self._check_same(o, "+")
        return Quantity(self.value + o.value, self.dims)

    def __sub__(self, o):
        o = _coerce_like(o, self)
        self._check_same(o, "-")
        return Quantity(self.value - o.value, self.dims)

    def __mul__(self, o):
        return Quantity(self.value * o.value, (self.dims[0] + o.dims[0], self.dims[1] + o.dims[1]))

    def __truediv__(self, o):
        if o.value == 0:
            raise ExpressionError("division by zero")
        return Quantity(self.value / o.value, (self.dims[0] - o.dims[0], self.dims[1] - o.dims[1]))

    def __pow__(self, o):
        if o.dims != SCALAR:
            raise ExpressionError("exponent must be unitless")
        e = o.value
        if self.dims != SCALAR and not float(e).is_integer():
            raise ExpressionError("fractional power of a dimensioned value")
        return Quantity(self.value ** e, (int(self.dims[0] * e), int(self.dims[1] * e)))

    def __neg__(self):
        return Quantity(-self.value, self.dims)


def _coerce_like(o: Quantity, ref: Quantity) -> Quantity:
    """A unitless operand added to a dimensioned one adopts its unit."""
    if o.dims == SCALAR and ref.dims != SCALAR:
        if ref.dims == ANGLE:
            return Quantity(o.value * _ANGLE_UNITS["deg"], ANGLE)
        return Quantity(o.value, ref.dims)
    return o


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

_FUNCS = {
    "sqrt": (math.sqrt, "same_half"),
    "abs": (abs, "same"),
    "min": (min, "same"),
    "max": (max, "same"),
    "floor": (math.floor, "same"),
    "ceil": (math.ceil, "same"),
    "round": (round, "same"),
    "sin": (math.sin, "trig"),
    "cos": (math.cos, "trig"),
    "tan": (math.tan, "trig"),
    "asin": (math.asin, "atrig"),
    "acos": (math.acos, "atrig"),
    "atan": (math.atan, "atrig"),
    "atan2": (math.atan2, "atrig2"),
    "ln": (math.log, "scalar"),
    "log": (math.log10, "scalar"),
    "exp": (math.exp, "scalar"),
}
_CONSTS = {"pi": Quantity(math.pi), "PI": Quantity(math.pi), "e": Quantity(math.e)}

# "10mm", "2.5 in", "30deg" -> insert multiplication with unit identifiers
_NUM_UNIT_RE = re.compile(r"(\d(?:[\d.]*)(?:[eE][+-]?\d+)?)\s*(mm|cm|m|um|inch|in|ft|yd|deg|rad|grad)\b")


def _preprocess(text: str) -> str:
    return _NUM_UNIT_RE.sub(lambda m: f"({m.group(1)}*__u_{m.group(2)})", text)


class _Evaluator:
    def __init__(self, lookup):
        self.lookup = lookup

    def visit(self, node):
        meth = getattr(self, "v_" + type(node).__name__, None)
        if meth is None:
            raise ExpressionError(f"unsupported syntax: {type(node).__name__}")
        return meth(node)

    def v_Expression(self, n):
        return self.visit(n.body)

    def v_Constant(self, n):
        if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
            raise ExpressionError("only numbers are allowed")
        return Quantity(float(n.value))

    def v_Name(self, n):
        name = n.id
        if name.startswith("__u_"):
            u = name[4:]
            if u in _LENGTH_UNITS:
                return Quantity(_LENGTH_UNITS[u], LENGTH)
            return Quantity(_ANGLE_UNITS[u], ANGLE)
        if name in _CONSTS:
            return _CONSTS[name]
        if name in _LENGTH_UNITS:  # bare unit, e.g. "2*in"
            return Quantity(_LENGTH_UNITS[name], LENGTH)
        if name in _ANGLE_UNITS:
            return Quantity(_ANGLE_UNITS[name], ANGLE)
        q = self.lookup(name) if self.lookup else None
        if q is None:
            raise ExpressionError(f"unknown parameter '{name}'")
        return q

    def v_UnaryOp(self, n):
        v = self.visit(n.operand)
        if isinstance(n.op, ast.USub):
            return -v
        if isinstance(n.op, ast.UAdd):
            return v
        raise ExpressionError("unsupported unary operator")

    def v_BinOp(self, n):
        a, b = self.visit(n.left), self.visit(n.right)
        op = n.op
        if isinstance(op, ast.Add):
            return a + b if a.dims != SCALAR else _coerce_like(a, b) + b
        if isinstance(op, ast.Sub):
            return a - b if a.dims != SCALAR else _coerce_like(a, b) - b
        if isinstance(op, ast.Mult):
            return a * b
        if isinstance(op, ast.Div):
            return a / b
        if isinstance(op, ast.Pow):
            return a ** b
        if isinstance(op, ast.Mod):
            if b.value == 0:
                raise ExpressionError("modulo by zero")
            return Quantity(math.fmod(a.value, b.value), a.dims)
        raise ExpressionError("unsupported operator")

    def v_Call(self, n):
        if not isinstance(n.func, ast.Name) or n.func.id not in _FUNCS:
            raise ExpressionError("unknown function")
        if n.keywords:
            raise ExpressionError("keyword arguments not allowed")
        fn, kind = _FUNCS[n.func.id]
        args = [self.visit(a) for a in n.args]
        if not args:
            raise ExpressionError("function needs arguments")
        try:
            if kind == "same":
                dims = args[0].dims
                args = [_coerce_like(a, args[0]) for a in args]
                if any(a.dims != dims for a in args):
                    raise ExpressionError("incompatible units")
                return Quantity(float(fn(*[a.value for a in args])), dims)
            if kind == "same_half":
                d = args[0].dims
                if d[0] % 2 or d[1] % 2:
                    raise ExpressionError("sqrt of odd unit power")
                return Quantity(fn(args[0].value), (d[0] // 2, d[1] // 2))
            if kind == "trig":
                a = args[0]
                rad = a.value if a.dims == ANGLE else a.value * _ANGLE_UNITS["deg"] if a.dims == SCALAR else None
                if rad is None:
                    raise ExpressionError("trig functions take angles")
                return Quantity(fn(rad))
            if kind == "atrig":
                return Quantity(fn(args[0].value), ANGLE)
            if kind == "atrig2":
                return Quantity(fn(args[0].value, args[1].value), ANGLE)
            if any(a.dims != SCALAR for a in args):
                raise ExpressionError("function takes unitless values")
            return Quantity(fn(*[a.value for a in args]))
        except (ValueError, OverflowError) as exc:
            raise ExpressionError(str(exc)) from None


def evaluate(text: str, lookup=None) -> Quantity:
    """Evaluate an expression string to a :class:`Quantity`."""
    text = str(text).strip()
    if not text:
        raise ExpressionError("empty expression")
    try:
        tree = ast.parse(_preprocess(text), mode="eval")
    except SyntaxError:
        raise ExpressionError(f"syntax error in '{text}'") from None
    return _Evaluator(lookup).visit(tree)


def names_in(text: str) -> set[str]:
    """Parameter names referenced by an expression (for dependency tracking)."""
    try:
        tree = ast.parse(_preprocess(str(text)), mode="eval")
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not node.id.startswith("__u_") \
                and node.id not in _CONSTS and node.id not in _LENGTH_UNITS \
                and node.id not in _ANGLE_UNITS and node.id not in _FUNCS:
            out.add(node.id)
    return out


def to_length(q: Quantity) -> float:
    if q.dims == SCALAR:
        return q.value  # bare number => mm
    if q.dims != LENGTH:
        raise ExpressionError("expected a length")
    return q.value


def to_angle(q: Quantity) -> float:
    """Return radians.  Bare numbers are degrees."""
    if q.dims == SCALAR:
        return q.value * _ANGLE_UNITS["deg"]
    if q.dims != ANGLE:
        raise ExpressionError("expected an angle")
    return q.value


def to_scalar(q: Quantity) -> float:
    if q.dims != SCALAR:
        raise ExpressionError("expected a unitless value")
    return q.value


def format_length(mm: float, unit: str = "mm", digits: int = 3) -> str:
    v = mm / _LENGTH_UNITS[unit]
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return f"{s} {unit}"


def format_angle(rad: float, digits: int = 2) -> str:
    s = f"{math.degrees(rad):.{digits}f}".rstrip("0").rstrip(".")
    return f"{s} deg"


IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def valid_param_name(name: str) -> bool:
    return bool(IDENT_RE.match(name)) and name not in _FUNCS and name not in _CONSTS \
        and name not in _LENGTH_UNITS and name not in _ANGLE_UNITS and not name.startswith("__")
