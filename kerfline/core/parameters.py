"""Parameter table (Fusion's *Change Parameters* dialog).

Two kinds of parameters live in one namespace:

* **user parameters** -- created explicitly (``width = 80 mm``)
* **model parameters** -- created automatically for every dimension and
  feature input (``d1``, ``d2`` ...) and owned by a feature.

Each feature input refers to a parameter by name, so a sketch dimension can
be driven by ``width / 2`` and the whole model updates when ``width`` does.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .expressions import (ExpressionError, Quantity, evaluate, names_in, to_angle,
                          to_length, to_scalar, valid_param_name)

KINDS = ("length", "angle", "scalar")


@dataclass
class Parameter:
    name: str
    expr: str
    kind: str = "length"
    owner: str | None = None  # feature id for model params, None = user param
    comment: str = ""
    favorite: bool = False

    def to_dict(self):
        return {"name": self.name, "expr": self.expr, "kind": self.kind,
                "owner": self.owner, "comment": self.comment, "favorite": self.favorite}

    @staticmethod
    def from_dict(d):
        return Parameter(d["name"], d["expr"], d.get("kind", "length"), d.get("owner"),
                         d.get("comment", ""), d.get("favorite", False))


@dataclass
class ParameterTable:
    params: dict[str, Parameter] = field(default_factory=dict)
    _counter: int = 0
    _cache: dict[str, float] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    def next_model_name(self) -> str:
        while True:
            self._counter += 1
            n = f"d{self._counter}"
            if n not in self.params:
                return n

    def add(self, expr: str, kind: str = "length", owner: str | None = None,
            name: str | None = None, comment: str = "") -> str:
        if name is None:
            name = self.next_model_name()
        elif not valid_param_name(name):
            raise ExpressionError(f"invalid parameter name '{name}'")
        elif name in self.params:
            raise ExpressionError(f"parameter '{name}' already exists")
        p = Parameter(name, str(expr), kind, owner, comment)
        self.params[name] = p
        try:
            self._check_cycles(name)
            self.value(name)
        except ExpressionError:
            del self.params[name]
            raise
        self._cache.clear()
        return name

    def set_expr(self, name: str, expr: str) -> None:
        p = self.params[name]
        old = p.expr
        p.expr = str(expr)
        self._cache.clear()
        try:
            self._check_cycles(name)
            self.value(name)
        except ExpressionError:
            p.expr = old
            self._cache.clear()
            raise

    def rename(self, old: str, new: str) -> None:
        if not valid_param_name(new) or new in self.params:
            raise ExpressionError(f"invalid or duplicate name '{new}'")
        p = self.params.pop(old)
        p.name = new
        self.params[new] = p
        # rewrite references in other expressions
        import re
        pat = re.compile(rf"\b{re.escape(old)}\b")
        for q in self.params.values():
            q.expr = pat.sub(new, q.expr)
        self._cache.clear()

    def remove(self, name: str) -> None:
        users = self.dependents(name)
        if users:
            raise ExpressionError(f"'{name}' is used by {', '.join(sorted(users))}")
        self.params.pop(name, None)
        self._cache.clear()

    def remove_owned_by(self, owner: str) -> None:
        for n in [n for n, p in self.params.items() if p.owner == owner]:
            # Inline the value into dependents so they keep working.
            deps = self.dependents(n)
            if deps:
                val = self.params[n].expr
                import re
                pat = re.compile(rf"\b{re.escape(n)}\b")
                for d in deps:
                    self.params[d].expr = pat.sub(f"({val})", self.params[d].expr)
            del self.params[n]
        self._cache.clear()

    def dependents(self, name: str) -> set[str]:
        return {n for n, p in self.params.items() if name in names_in(p.expr)}

    # ------------------------------------------------------------------
    def _check_cycles(self, start: str) -> None:
        seen, stack = set(), [(start, iter(names_in(self.params[start].expr)))]
        path = [start]
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                path.pop()
                seen.add(node)
                continue
            if nxt in path:
                raise ExpressionError(f"circular reference: {' -> '.join(path + [nxt])}")
            if nxt in self.params and nxt not in seen:
                stack.append((nxt, iter(names_in(self.params[nxt].expr))))
                path.append(nxt)

    def quantity(self, name: str, _depth: int = 0) -> Quantity:
        if _depth > 200:
            raise ExpressionError("expression nesting too deep")
        p = self.params.get(name)
        if p is None:
            raise ExpressionError(f"unknown parameter '{name}'")
        q = evaluate(p.expr, lambda n: self._lookup(n, _depth + 1))
        # Bare numbers adopt the parameter's kind
        if q.dims == (0, 0) and p.kind == "length":
            q = Quantity(q.value, (1, 0))
        elif q.dims == (0, 0) and p.kind == "angle":
            q = Quantity(to_angle(q), (0, 1))
        return q

    def _lookup(self, n: str, depth: int):
        if n not in self.params:
            return None
        return self.quantity(n, depth)

    def value(self, name: str) -> float:
        """Base-unit value (mm, rad or scalar)."""
        if name in self._cache:
            return self._cache[name]
        q = self.quantity(name)
        kind = self.params[name].kind
        v = to_length(q) if kind == "length" else to_angle(q) if kind == "angle" else to_scalar(q)
        self._cache[name] = v
        return v

    def eval_expr(self, expr: str, kind: str = "length") -> float:
        q = evaluate(expr, lambda n: self._lookup(n, 0))
        return to_length(q) if kind == "length" else to_angle(q) if kind == "angle" else to_scalar(q)

    def user_params(self):
        return [p for p in self.params.values() if p.owner is None]

    def model_params(self):
        return [p for p in self.params.values() if p.owner is not None]

    # ------------------------------------------------------------------
    def to_dict(self):
        return {"counter": self._counter, "params": [p.to_dict() for p in self.params.values()]}

    @staticmethod
    def from_dict(d):
        t = ParameterTable()
        t._counter = d.get("counter", 0)
        for pd in d.get("params", []):
            p = Parameter.from_dict(pd)
            t.params[p.name] = p
        return t
