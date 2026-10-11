"""Thread standards for cosmetic threads and tapped holes.

Data: ISO 261 metric coarse/fine and ASME B1.1 unified (UNC/UNF), as
(designation -> major diameter mm, pitch mm, tap drill mm).
"""
from __future__ import annotations

# (major dia mm, pitch mm, tap drill mm)
METRIC = {
    "M2x0.4": (2.0, 0.4, 1.6), "M2.5x0.45": (2.5, 0.45, 2.05), "M3x0.5": (3.0, 0.5, 2.5), "M4x0.7": (4.0, 0.7, 3.3),
    "M5x0.8": (5.0, 0.8, 4.2), "M6x1": (6.0, 1.0, 5.0), "M8x1.25": (8.0, 1.25, 6.8), "M10x1.5": (10.0, 1.5, 8.5),
    "M12x1.75": (12.0, 1.75, 10.2), "M14x2": (14.0, 2.0, 12.0), "M16x2": (16.0, 2.0, 14.0),
    "M20x2.5": (20.0, 2.5, 17.5), "M24x3": (24.0, 3.0, 21.0),
    "M6x0.75": (6.0, 0.75, 5.25), "M8x1": (8.0, 1.0, 7.0), "M10x1.25": (10.0, 1.25, 8.75),
    "M12x1.5": (12.0, 1.5, 10.5), "M16x1.5": (16.0, 1.5, 14.5), "M20x1.5": (20.0, 1.5, 18.5),
}
UNIFIED = {
    "#4-40 UNC": (2.845, 0.635, 2.35), "#6-32 UNC": (3.505, 0.794, 2.85), "#8-32 UNC": (4.166, 0.794, 3.5),
    "#10-24 UNC": (4.826, 1.058, 3.9), "#10-32 UNF": (4.826, 0.794, 4.1), "1/4-20 UNC": (6.35, 1.27, 5.1),
    "1/4-28 UNF": (6.35, 0.907, 5.5), "5/16-18 UNC": (7.938, 1.411, 6.6), "3/8-16 UNC": (9.525, 1.588, 8.0),
    "1/2-13 UNC": (12.7, 1.954, 10.8), "5/8-11 UNC": (15.875, 2.309, 13.5), "3/4-10 UNC": (19.05, 2.54, 16.5),
}
THREADS = {**METRIC, **UNIFIED}


def info(designation: str) -> dict:
    if designation not in THREADS:
        raise KeyError(f"unknown thread '{designation}'")
    major, pitch, drill = THREADS[designation]
    return {"designation": designation, "major": major, "pitch": pitch, "tap_drill": drill,
            "minor": major - 1.0825 * pitch}


def nearest(diameter_mm: float, internal: bool) -> str:
    """Designation whose major (external) or tap-drill (internal) diameter is closest."""
    idx = 2 if internal else 0
    return min(THREADS, key=lambda k: abs(THREADS[k][idx] - diameter_mm))


def label(designation: str, length: float | None = None, internal: bool = True) -> str:
    txt = designation
    if length:
        txt += f" x {length:.3g}"
    return txt + (" (int)" if internal else " (ext)")
