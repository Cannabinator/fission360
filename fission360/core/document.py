"""Parametric design document: timeline, parameters, bodies, undo/redo.

The document is the single source of truth.  Its persistent state is a list
of features (the *timeline*), a parameter table and a few per-body display
properties.  Geometry is never stored -- it is *derived* by replaying the
timeline -- except for imported bodies which embed their B-rep.

Rebuilds are incremental: each feature gets a fingerprint made from its own
definition plus the values of every parameter it uses.  On rebuild we replay
from the first feature whose fingerprint changed and reuse cached model
states (shape handles are immutable, so caching them is cheap) for
everything before it.
"""
from __future__ import annotations

import copy
import itertools
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np

from . import kernel as K
from .expressions import ExpressionError, names_in
from .parameters import ParameterTable
from ..sketch.model import Sketch

FILE_VERSION = 1
_token = itertools.count(1)

PALETTE = [(0.70, 0.72, 0.75), (0.55, 0.68, 0.85), (0.85, 0.62, 0.45), (0.58, 0.80, 0.60),
           (0.85, 0.75, 0.45), (0.75, 0.60, 0.85), (0.50, 0.80, 0.80), (0.88, 0.55, 0.60)]


@dataclass
class Body:
    id: str
    shape: object
    token: int = field(default_factory=lambda: next(_token))  # changes whenever geometry changes

    def with_shape(self, shape) -> "Body":
        return Body(self.id, shape)


@dataclass
class SketchOut:
    frame: K.Frame
    sketch: Sketch
    _profiles: list | None = None

    @property
    def profiles(self):
        if self._profiles is None:
            self._profiles = K.build_profiles(self.sketch, self.frame)
        return self._profiles


@dataclass
class ModelState:
    bodies: dict = field(default_factory=dict)       # id -> Body (insertion ordered)
    sketches: dict = field(default_factory=dict)     # feature id -> SketchOut
    planes: dict = field(default_factory=dict)       # feature id -> Frame
    axes: dict = field(default_factory=dict)         # feature id -> (origin, dir)
    body_order: list = field(default_factory=list)   # creation order for default names
    annotations: list = field(default_factory=list)  # cosmetic threads etc. (labels in the viewport)

    def copy(self) -> "ModelState":
        return ModelState(dict(self.bodies), dict(self.sketches), dict(self.planes), dict(self.axes),
                          list(self.body_order), list(self.annotations))

    def add_body(self, bid: str, shape) -> Body:
        b = Body(bid, shape)
        self.bodies[bid] = b
        if bid not in self.body_order:
            self.body_order.append(bid)
        return b

    def set_shape(self, bid: str, shape):
        self.bodies[bid] = self.bodies[bid].with_shape(shape)

    def remove_body(self, bid: str):
        self.bodies.pop(bid, None)


@dataclass
class Feature:
    id: str
    type: str
    name: str
    data: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)   # input key -> parameter name
    suppressed: bool = False
    error: str | None = None
    error_kind: str | None = None                # "reference" when a face/edge/profile could not be re-found
    warning: str | None = None
    sketch: Sketch | None = None                 # live sketch object (type == sketch)

    def to_dict(self):
        d = {"id": self.id, "type": self.type, "name": self.name, "data": copy.deepcopy(self.data),
             "params": dict(self.params)}
        if self.suppressed:
            d["suppressed"] = True
        if self.sketch is not None:
            d["data"]["sketch"] = self.sketch.to_dict()
        return d

    @staticmethod
    def from_dict(d) -> "Feature":
        f = Feature(d["id"], d["type"], d["name"], copy.deepcopy(d.get("data", {})), dict(d.get("params", {})),
                    d.get("suppressed", False))
        if f.type == "sketch":
            f.sketch = Sketch.from_dict(f.data.pop("sketch", None) or Sketch().to_dict())
        return f

    def used_params(self) -> set:
        s = set(self.params.values())
        if self.sketch is not None:
            s.update(self.sketch.dimension_params())
        return s


class Document:
    def __init__(self):
        self.params = ParameterTable()
        self.features: list[Feature] = []
        self.marker = 0                     # number of active features
        self.body_props: dict[str, dict] = {}
        self.units = "mm"
        self.path: str | None = None
        self.name = "Untitled"
        self.modified = False
        self._fid = 0
        self._states: list[ModelState | None] = []
        self._prints: list[str | None] = []
        self.state = ModelState()
        self.listeners: list = []
        self._undo: list[tuple[str, dict]] = []
        self._redo: list[tuple[str, dict]] = []
        self._txn_depth = 0
        self._txn_snapshot = None
        self.last_rebuild_ms = 0.0
        self.versions: list[dict] = []      # named snapshots: {"name", "time", "data"}

    # ------------------------------------------------------------------ events
    def notify(self, what="changed"):
        for cb in list(self.listeners):
            cb(what)

    # ------------------------------------------------------------------ features
    def new_id(self) -> str:
        self._fid += 1
        return f"f{self._fid}"

    def feature(self, fid: str) -> Feature | None:
        return next((f for f in self.features if f.id == fid), None)

    def index_of(self, fid: str) -> int:
        return next(i for i, f in enumerate(self.features) if f.id == fid)

    def default_name(self, ftype: str) -> str:
        from .features import FEATURE_TYPES
        base = FEATURE_TYPES.get(ftype, {}).get("label", ftype.title()).replace(" ", "")
        n = 1
        names = {f.name for f in self.features}
        while f"{base}{n}" in names:
            n += 1
        return f"{base}{n}"

    def add_feature(self, ftype: str, data: dict, numeric: dict | None = None, name: str | None = None,
                    sketch: Sketch | None = None) -> Feature:
        """Insert a feature at the timeline marker.

        ``numeric`` maps input keys to ``(expression, kind)``; a model
        parameter is created for each (``d1``, ``d2`` ...).
        """
        f = Feature(self.new_id(), ftype, name or self.default_name(ftype), copy.deepcopy(data))
        for key, (expr, kind) in (numeric or {}).items():
            f.params[key] = self.params.add(expr, kind, owner=f.id)
        if ftype == "sketch":
            f.sketch = sketch or Sketch()
        self.features.insert(self.marker, f)
        self._states.insert(self.marker, None)
        self._prints.insert(self.marker, None)
        self.marker += 1
        self.rebuild()
        return f

    def insert_feature(self, f: Feature, index: int | None = None):
        """Insert a prepared feature (params already created) at the marker."""
        i = self.marker if index is None else index
        self.features.insert(i, f)
        self._states.insert(i, None)
        self._prints.insert(i, None)
        if i < self.marker or index is None:
            self.marker += 1
        if f.sketch is not None:
            f.sketch.param_value = self.param_value
        self.rebuild()
        return f

    def push_undo(self, label: str, snap: dict):
        """Record an undo step for edits made outside ``transaction``."""
        self._undo.append((label, snap))
        self._redo.clear()
        if len(self._undo) > 200:
            self._undo.pop(0)
        self.modified = True
        self.notify("history")

    def update_feature(self, f: Feature, data: dict | None = None, numeric: dict | None = None):
        if data is not None:
            f.data = copy.deepcopy(data)
        for key, (expr, kind) in (numeric or {}).items():
            if key in f.params:
                self.params.set_expr(f.params[key], expr)
            else:
                f.params[key] = self.params.add(expr, kind, owner=f.id)
        self.rebuild()

    def delete_feature(self, fid: str):
        i = self.index_of(fid)
        f = self.features.pop(i)
        self._states.pop(i)
        self._prints.pop(i)
        if i < self.marker:
            self.marker -= 1
        self.params.remove_owned_by(f.id)
        self.rebuild()

    def move_feature(self, fid: str, new_index: int):
        i = self.index_of(fid)
        f = self.features.pop(i)
        new_index = max(0, min(new_index, len(self.features)))
        self.features.insert(new_index, f)
        self._states = [None] * len(self.features)
        self._prints = [None] * len(self.features)
        self.rebuild()

    def set_marker(self, n: int):
        self.marker = max(0, min(n, len(self.features)))
        self.rebuild()

    def set_suppressed(self, fid: str, value: bool):
        self.feature(fid).suppressed = value
        self.rebuild()

    def rename_feature(self, fid: str, name: str):
        self.feature(fid).name = name
        self.notify("renamed")

    # ------------------------------------------------------------------ parameters
    def param_value(self, name: str) -> float:
        return self.params.value(name)

    def set_param(self, name: str, expr: str):
        self.params.set_expr(name, expr)
        self.rebuild()

    def val(self, f: Feature, key: str, default=None) -> float:
        pname = f.params.get(key)
        if pname is None:
            if default is None:
                raise ExpressionError(f"missing input '{key}'")
            return default
        return self.params.value(pname)

    def expr(self, f: Feature, key: str) -> str:
        return self.params.params[f.params[key]].expr

    # ------------------------------------------------------------------ rebuild
    def _fingerprint(self, f: Feature) -> str:
        vals = {}
        for p in sorted(f.used_params()):
            try:
                vals[p] = round(self.params.value(p), 12)
            except ExpressionError as exc:
                vals[p] = f"ERR:{exc}"
        return json.dumps([f.to_dict(), vals], sort_keys=True, default=str)

    def rebuild(self, force=False):
        from .features import execute
        t0 = time.perf_counter()
        self.params._cache.clear()
        n = len(self.features)
        if len(self._states) != n:
            self._states = [None] * n
            self._prints = [None] * n
        # Cumulative fingerprints: a cached state is valid only if the feature
        # *and everything before it* (incl. order/suppression) is unchanged.
        import hashlib
        prints, h = [], hashlib.sha1()
        for f in self.features:
            h.update(self._fingerprint(f).encode())
            prints.append(h.hexdigest())
        start = 0
        if not force:
            while start < min(n, self.marker) and self._states[start] is not None and prints[start] == self._prints[start]:
                start += 1
        state = self._states[start - 1] if start > 0 else ModelState()
        for i in range(start, n):
            f = self.features[i]
            if i >= self.marker:
                self._states[i] = None
                self._prints[i] = None
                continue
            if f.suppressed:
                f.error = None
                f.error_kind = None
                if f.sketch is not None:
                    f.sketch.param_value = self.param_value
            else:
                new = state.copy()
                try:
                    f.warning = None
                    execute(self, f, new)
                    f.error = None
                    f.error_kind = None
                    state = new
                except Exception as exc:  # feature failed: keep previous state
                    from .references import ReferenceError_
                    f.error = str(exc) or type(exc).__name__
                    f.error_kind = "reference" if isinstance(exc, ReferenceError_) else None
            self._states[i] = state
            self._prints[i] = prints[i]
        self.state = state if self.marker > 0 or n == 0 else ModelState()
        if self.marker == 0:
            self.state = ModelState()
        self.last_rebuild_ms = (time.perf_counter() - t0) * 1000
        self.modified = True
        self.notify("rebuilt")

    def state_before(self, fid: str) -> ModelState:
        """Model state just before a feature (used when editing it)."""
        i = self.index_of(fid)
        if i == 0:
            return ModelState()
        s = self._states[i - 1]
        if s is None:
            # Not computed (beyond the marker) -- compute on demand
            saved = self.marker
            self.marker = i
            self.rebuild()
            s = self._states[i - 1]
            self.marker = saved
            self.rebuild()
        return s

    # ------------------------------------------------------------------ bodies
    def body_name(self, bid: str) -> str:
        p = self.body_props.get(bid, {})
        if "name" in p:
            return p["name"]
        try:
            return f"Body{self.state.body_order.index(bid) + 1}"
        except ValueError:
            return bid

    def body_visible(self, bid: str) -> bool:
        return self.body_props.get(bid, {}).get("visible", True)

    def body_color(self, bid: str):
        p = self.body_props.get(bid, {})
        if "color" in p:
            return tuple(p["color"])
        try:
            i = self.state.body_order.index(bid)
        except ValueError:
            i = 0
        return PALETTE[0] if i == 0 else PALETTE[i % len(PALETTE)]

    def set_body_prop(self, bid: str, key: str, value):
        self.body_props.setdefault(bid, {})[key] = value
        self.modified = True
        self.notify("display")

    def body_material(self, bid: str) -> str:
        return self.body_props.get(bid, {}).get("material", "Steel")

    # ------------------------------------------------------------------ undo/redo
    def snapshot(self) -> dict:
        return self.to_dict()

    def restore(self, snap: dict):
        fresh = Document.from_dict(snap)
        old = {f.id: (pr, st) for f, pr, st in zip(self.features, self._prints, self._states)}
        self.params = fresh.params
        self.features = fresh.features
        self.marker = fresh.marker
        self.body_props = fresh.body_props
        self._fid = max(self._fid, fresh._fid)   # versions stay as they are (not part of a snapshot)
        # keep cached states for unchanged prefix (fingerprints decide)
        self._prints = [old.get(f.id, (None, None))[0] for f in self.features]
        self._states = [old.get(f.id, (None, None))[1] for f in self.features]
        # cached states are only valid in order; invalidate after first mismatch
        self.rebuild()

    @contextmanager
    def transaction(self, label: str):
        """Group modifications into one undoable step."""
        if self._txn_depth == 0:
            self._txn_snapshot = self.snapshot()
        self._txn_depth += 1
        try:
            yield
        except Exception:
            self._txn_depth -= 1
            if self._txn_depth == 0:
                snap, self._txn_snapshot = self._txn_snapshot, None
                self.restore(snap)
            raise
        self._txn_depth -= 1
        if self._txn_depth == 0:
            snap, self._txn_snapshot = self._txn_snapshot, None
            if json.dumps(snap, sort_keys=True) != json.dumps(self.snapshot(), sort_keys=True):
                self._undo.append((label, snap))
                self._redo.clear()
                if len(self._undo) > 200:
                    self._undo.pop(0)
            self.notify("history")

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo_label(self):
        return self._undo[-1][0] if self._undo else ""

    def redo_label(self):
        return self._redo[-1][0] if self._redo else ""

    def undo(self):
        if not self._undo:
            return
        label, snap = self._undo.pop()
        self._redo.append((label, self.snapshot()))
        self.restore(snap)
        self.notify("history")

    def redo(self):
        if not self._redo:
            return
        label, snap = self._redo.pop()
        self._undo.append((label, self.snapshot()))
        self.restore(snap)
        self.notify("history")

    # ------------------------------------------------------------------ persistence
    def to_dict(self, include_versions: bool = False) -> dict:
        d = {"format": "fission360", "version": FILE_VERSION, "units": self.units, "fid": self._fid,
             "marker": self.marker, "parameters": self.params.to_dict(),
             "features": [f.to_dict() for f in self.features], "bodies": copy.deepcopy(self.body_props)}
        if include_versions and self.versions:
            d["versions"] = copy.deepcopy(self.versions)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Document":
        if d.get("format") != "fission360":
            raise ValueError("not a Fission360 document")
        doc = Document()
        doc.units = d.get("units", "mm")
        doc._fid = d.get("fid", 0)
        doc.params = ParameterTable.from_dict(d.get("parameters", {}))
        doc.features = [Feature.from_dict(fd) for fd in d.get("features", [])]
        doc.marker = d.get("marker", len(doc.features))
        doc.body_props = d.get("bodies", {})
        doc.versions = copy.deepcopy(d.get("versions", []))
        for f in doc.features:
            if f.sketch is not None:
                f.sketch.param_value = doc.param_value
        doc._states = [None] * len(doc.features)
        doc._prints = [None] * len(doc.features)
        return doc

    def save(self, path: str, compress: bool = False):
        """Save as plain, sorted, indented JSON so designs diff and merge well in
        Git.  ``compress=True`` writes gzip instead (smaller, not diffable)."""
        import gzip
        data = json.dumps(self.to_dict(include_versions=True), sort_keys=True, indent=1,
                          ensure_ascii=False).encode() + b"\n"
        tmp = path + ".tmp"
        if compress:
            with gzip.open(tmp, "wb", compresslevel=6) as fh:
                fh.write(data)
        else:
            with open(tmp, "wb") as fh:
                fh.write(data)
        import os
        os.replace(tmp, path)          # atomic: a crash never leaves a half-written file
        self.path = path
        self.modified = False
        self.notify("saved")

    @staticmethod
    def load(path: str) -> "Document":
        import gzip
        with open(path, "rb") as fh:
            raw = fh.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        doc = Document.from_dict(json.loads(raw.decode()))
        doc.path = path
        import os
        doc.name = os.path.splitext(os.path.basename(path))[0]
        doc.rebuild()
        doc.modified = False
        return doc

    # ------------------------------------------------------------------ versions
    def save_version(self, name: str) -> dict:
        import time as _t
        v = {"name": name, "time": _t.strftime("%Y-%m-%d %H:%M:%S"), "data": self.to_dict()}
        self.versions.append(v)
        self.modified = True
        self.notify("history")
        return v

    def restore_version(self, index: int):
        """Roll the design back to a named version (undoable)."""
        snap = self.snapshot()
        self.restore(self.versions[index]["data"])
        self.push_undo(f"Restore version '{self.versions[index]['name']}'", snap)

    @staticmethod
    def diff(a: dict, b: dict) -> list[str]:
        """Feature-level difference between two design dicts (a -> b)."""
        fa = {f["id"]: f for f in a.get("features", [])}
        fb = {f["id"]: f for f in b.get("features", [])}
        out = []
        for fid, f in fb.items():
            if fid not in fa:
                out.append(f"+ added {f['name']} ({f['type']})")
        for fid, f in fa.items():
            if fid not in fb:
                out.append(f"- removed {f['name']} ({f['type']})")
        pa = {p["name"]: p["expr"] for p in a.get("parameters", {}).get("params", [])}
        pb = {p["name"]: p["expr"] for p in b.get("parameters", {}).get("params", [])}
        for fid, f in fb.items():
            if fid in fa and json.dumps(fa[fid]["data"], sort_keys=True) != json.dumps(f["data"], sort_keys=True):
                out.append(f"~ changed {f['name']} (inputs)")
        for n, e in pb.items():
            if n in pa and pa[n] != e:
                out.append(f"~ parameter {n}: {pa[n]} -> {e}")
            elif n not in pa:
                out.append(f"+ parameter {n} = {e}")
        for n in pa:
            if n not in pb:
                out.append(f"- parameter {n}")
        if [f["id"] for f in a.get("features", []) if f["id"] in fb] != [f["id"] for f in b.get("features", []) if f["id"] in fa]:
            out.append("~ timeline order changed")
        return out or ["(no differences)"]

    # ------------------------------------------------------------------ queries
    def visible_bodies(self):
        return [b for b in self.state.bodies.values() if self.body_visible(b.id)]

    def all_param_users(self, pname: str) -> list[Feature]:
        closure = {pname}
        frontier = [pname]
        while frontier:
            n = frontier.pop()
            for d in self.params.dependents(n):
                if d not in closure:
                    closure.add(d)
                    frontier.append(d)
        return [f for f in self.features if f.used_params() & closure]

    def unused_names(self, text: str) -> set:
        return {n for n in names_in(text) if n not in self.params.params}

    # ------------------------------------------------------------------ components
    def component_of(self, bid: str) -> str | None:
        return self.body_props.get(bid, {}).get("component") or None

    def components(self) -> dict:
        """Component name -> [body ids] for the current model."""
        out: dict = {}
        for bid in self.state.bodies:
            c = self.component_of(bid)
            if c:
                out.setdefault(c, []).append(bid)
        return out

    def set_component(self, bids, name: str | None):
        for bid in bids:
            if name:
                self.body_props.setdefault(bid, {})["component"] = name
            else:
                self.body_props.get(bid, {}).pop("component", None)
        self.modified = True
        self.notify("props")

    def export_bodies(self, path: str, bodies=None):
        import os
        bodies = bodies or self.visible_bodies()
        if not bodies:
            raise K.KernelError("nothing to export")
        ext = os.path.splitext(path)[1].lower()
        shapes = [b.shape for b in bodies]
        if ext in (".step", ".stp"):
            if any(self.component_of(b.id) for b in bodies):
                tree: dict = {}
                for b in bodies:
                    tree.setdefault(self.component_of(b.id), []).append((self.body_name(b.id), b.shape))
                K.export_step_assembly(list(tree.items()), path)
            else:
                K.export_step([(self.body_name(b.id), b.shape) for b in bodies], path)
        elif ext in (".iges", ".igs"):
            K.export_iges(shapes, path)
        elif ext == ".stl":
            K.export_stl(K.compound(shapes), path)
        elif ext == ".3mf":
            K.export_3mf([(self.body_name(b.id), b.shape) for b in bodies], path)
        elif ext == ".brep":
            K.export_brep(K.compound(shapes), path)
        elif ext == ".obj":
            export_obj(self, bodies, path)
        else:
            raise K.KernelError(f"unsupported export format '{ext}'")


def export_obj(doc, bodies, path):
    with open(path, "w") as fh:
        fh.write("# Fission360 OBJ export\n")
        base = 1
        for b in bodies:
            m = K.tessellate(b.shape)
            fh.write(f"o {doc.body_name(b.id)}\n")
            for p in m.positions:
                fh.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
            for n in m.normals:
                fh.write(f"vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}\n")
            for t in m.indices + base:
                fh.write(f"f {t[0]}//{t[0]} {t[1]}//{t[1]} {t[2]}//{t[2]}\n")
            base += len(m.positions)


def np_round(v, n=6):
    return np.round(np.asarray(v, float), n).tolist()
