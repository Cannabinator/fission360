"""Vector icons (inline SVG, rendered and cached at the display's DPI)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

B = "#2a6fd1"   # blue
O = "#e8892b"   # orange
G = "#6b7380"   # grey
D = "#2c323b"   # dark
S = "#b9c7da"   # solid fill
R = "#d64545"   # red
GR = "#3a9a52"  # green

_BODY = f'fill="{S}" stroke="{D}" stroke-width="1.1" stroke-linejoin="round"'

ICONS = {
    "sketch": f'<rect x="3" y="4" width="15" height="15" fill="none" stroke="{B}" stroke-width="1.6"/>'
              f'<path d="M14 18 L21 6 L22.5 7.5 L15.5 19.5 Z" fill="{O}" stroke="{D}" stroke-width=".8"/>',
    "finish": f'<circle cx="12" cy="12" r="9" fill="{GR}"/><path d="M7 12.5 L10.5 16 L17 8.5" fill="none" stroke="white" stroke-width="2.2"/>',
    "extrude": f'<path d="M4 15 L12 19 L20 15 L12 11 Z" fill="{B}" opacity=".35" stroke="{B}"/>'
               f'<path d="M4 8 L12 12 L20 8 L20 15 L12 19 L4 15 Z" {_BODY}/>'
               f'<path d="M4 8 L12 4 L20 8 L12 12 Z" fill="#dfe8f5" stroke="{D}" stroke-width="1.1"/>'
               f'<path d="M12 9 V2 M9.5 4.5 L12 2 L14.5 4.5" stroke="{O}" stroke-width="1.6" fill="none"/>',
    "revolve": f'<ellipse cx="12" cy="16" rx="8" ry="3" fill="none" stroke="{B}" stroke-width="1.3"/>'
               f'<path d="M4 16 V8 Q12 3 20 8 V16" {_BODY}/><path d="M12 2 V22" stroke="{O}" stroke-dasharray="2 1.5" stroke-width="1.3"/>',
    "sweep": f'<path d="M4 18 Q8 4 20 6" fill="none" stroke="{O}" stroke-width="1.5" stroke-dasharray="2 1.5"/>'
             f'<path d="M3 16 Q8 2 21 4 L20 9 Q10 8 6 19 Z" {_BODY}/>',
    "loft": f'<rect x="4" y="16" width="10" height="5" fill="none" stroke="{B}" stroke-width="1.3"/>'
            f'<circle cx="15" cy="6" r="4" fill="none" stroke="{B}" stroke-width="1.3"/>'
            f'<path d="M4 16 L11 6 M14 16 L19 6" stroke="{D}" stroke-width="1.1"/>',
    "hole": f'<path d="M3 9 L12 5 L21 9 L21 16 L12 20 L3 16 Z" {_BODY}/>'
            f'<ellipse cx="12" cy="9.5" rx="4" ry="2" fill="{D}"/>',
    "fillet": f'<path d="M4 20 V10 Q4 4 10 4 H20 V20 Z" {_BODY}/><path d="M4 10 Q4 4 10 4" fill="none" stroke="{O}" stroke-width="2"/>',
    "chamfer": f'<path d="M4 20 V10 L10 4 H20 V20 Z" {_BODY}/><path d="M4 10 L10 4" stroke="{O}" stroke-width="2"/>',
    "shell": f'<path d="M3 7 L12 3 L21 7 V17 L12 21 L3 17 Z" {_BODY}/><path d="M6 8 L12 5.5 L18 8 L12 10.5 Z" fill="{G}"/>',
    "draft": f'<path d="M6 20 L9 5 H15 L18 20 Z" {_BODY}/><path d="M12 3 V21" stroke="{O}" stroke-dasharray="2 1.5"/>',
    "box": f'<path d="M3 8 L12 4 L21 8 V16 L12 20 L3 16 Z" {_BODY}/><path d="M3 8 L12 12 L21 8 M12 12 V20" stroke="{D}" fill="none"/>',
    "cylinder": f'<path d="M5 6 V18 A7 3 0 0 0 19 18 V6" {_BODY}/><ellipse cx="12" cy="6" rx="7" ry="3" fill="#dfe8f5" stroke="{D}"/>',
    "sphere": f'<circle cx="12" cy="12" r="8.5" {_BODY}/><ellipse cx="12" cy="12" rx="8.5" ry="3" fill="none" stroke="{D}" stroke-width=".8"/>',
    "torus": f'<ellipse cx="12" cy="12" rx="9.5" ry="6" {_BODY}/><ellipse cx="12" cy="11.5" rx="4" ry="2" fill="#f3f4f6" stroke="{D}"/>',
    "coil": f'<path d="M5 19 Q19 17 12 15 Q5 13 19 11 Q5 9 12 7 Q19 5 5 3" fill="none" stroke="{B}" stroke-width="2.4"/>',
    "pattern_rect": "".join(f'<rect x="{x}" y="{y}" width="5" height="5" {_BODY}/>' for x in (3, 10, 17) for y in (4, 14)),
    "pattern_circ": "".join(f'<circle cx="{12 + 7 * c}" cy="{12 + 7 * s}" r="2.6" {_BODY}/>' for c, s in
                            ((1, 0), (0.5, 0.87), (-0.5, 0.87), (-1, 0), (-0.5, -0.87), (0.5, -0.87))),
    "mirror": f'<path d="M3 6 L9 9 V18 L3 15 Z" {_BODY}/><path d="M21 6 L15 9 V18 L21 15 Z" {_BODY} opacity=".6"/>'
              f'<path d="M12 2 V22" stroke="{O}" stroke-dasharray="2 1.5" stroke-width="1.4"/>',
    "combine": f'<circle cx="9" cy="12" r="6" {_BODY}/><circle cx="15" cy="12" r="6" {_BODY} opacity=".8"/>',
    "move": f'<path d="M12 2 V22 M2 12 H22 M12 2 L9.5 5 M12 2 L14.5 5 M12 22 L9.5 19 M12 22 L14.5 19 '
            f'M2 12 L5 9.5 M2 12 L5 14.5 M22 12 L19 9.5 M22 12 L19 14.5" stroke="{D}" stroke-width="1.5" fill="none"/>',
    "scale": f'<rect x="3" y="11" width="10" height="10" {_BODY}/><path d="M11 13 L20 4 M14 4 H20 V10" stroke="{O}" stroke-width="1.6" fill="none"/>',
    "split": f'<path d="M3 8 L12 4 L21 8 V16 L12 20 L3 16 Z" {_BODY}/><path d="M2 14 L22 9" stroke="{R}" stroke-width="1.8"/>',
    "remove": f'<path d="M6 7 H18 L17 21 H7 Z" {_BODY}/><path d="M4 7 H20 M9 7 V4 H15 V7" stroke="{D}" fill="none" stroke-width="1.3"/>',
    "plane": f'<path d="M2 15 L9 6 H22 L15 15 Z" fill="{O}" opacity=".35" stroke="{O}" stroke-width="1.3"/>',
    "axis": f'<path d="M4 20 L20 4" stroke="{O}" stroke-width="1.8" stroke-dasharray="3 1.5"/>',
    "import": f'<path d="M5 4 H14 L19 9 V20 H5 Z" fill="white" stroke="{D}"/><path d="M12 9 V17 M8.5 13.5 L12 17 L15.5 13.5" stroke="{B}" stroke-width="1.8" fill="none"/>',
    "export": f'<path d="M5 4 H14 L19 9 V20 H5 Z" fill="white" stroke="{D}"/><path d="M12 17 V9 M8.5 12.5 L12 9 L15.5 12.5" stroke="{GR}" stroke-width="1.8" fill="none"/>',
    "line": f'<path d="M4 20 L20 4" stroke="{B}" stroke-width="1.8"/><rect x="2.5" y="18.5" width="3" height="3" fill="{D}"/><rect x="18.5" y="2.5" width="3" height="3" fill="{D}"/>',
    "rect": f'<rect x="4" y="6" width="16" height="12" fill="none" stroke="{B}" stroke-width="1.8"/>',
    "rect_center": f'<rect x="4" y="6" width="16" height="12" fill="none" stroke="{B}" stroke-width="1.8"/><circle cx="12" cy="12" r="1.6" fill="{D}"/>',
    "circle": f'<circle cx="12" cy="12" r="8" fill="none" stroke="{B}" stroke-width="1.8"/><circle cx="12" cy="12" r="1.5" fill="{D}"/>',
    "circle2p": f'<circle cx="12" cy="12" r="8" fill="none" stroke="{B}" stroke-width="1.8"/><circle cx="4" cy="12" r="1.6" fill="{D}"/><circle cx="20" cy="12" r="1.6" fill="{D}"/>',
    "arc": f'<path d="M4 18 A9 9 0 0 1 20 18" fill="none" stroke="{B}" stroke-width="1.8"/><circle cx="4" cy="18" r="1.6" fill="{D}"/><circle cx="20" cy="18" r="1.6" fill="{D}"/><circle cx="12" cy="9" r="1.6" fill="{D}"/>',
    "arc_center": f'<path d="M20 12 A8 8 0 0 0 12 4" fill="none" stroke="{B}" stroke-width="1.8"/><circle cx="12" cy="12" r="1.6" fill="{D}"/>',
    "polygon": f'<path d="M12 3 L20 8 V16 L12 21 L4 16 V8 Z" fill="none" stroke="{B}" stroke-width="1.8"/>',
    "slot": f'<path d="M7 8 H17 A4 4 0 0 1 17 16 H7 A4 4 0 0 1 7 8 Z" fill="none" stroke="{B}" stroke-width="1.8"/>',
    "spline": f'<path d="M3 18 C7 2 13 22 21 6" fill="none" stroke="{B}" stroke-width="1.8"/>',
    "point": f'<path d="M12 6 V18 M6 12 H18" stroke="{B}" stroke-width="1.5"/><circle cx="12" cy="12" r="2.2" fill="{D}"/>',
    "trim": f'<path d="M3 12 H21" stroke="{B}" stroke-width="1.8"/><path d="M12 3 V21" stroke="{G}" stroke-width="1.4"/>'
            f'<path d="M14 6 L20 9 M14 9 L20 6" stroke="{R}" stroke-width="1.6"/>',
    "sketch_fillet": f'<path d="M4 20 V12 Q4 4 12 4 H20" fill="none" stroke="{B}" stroke-width="1.8"/>',
    "offset": f'<path d="M4 20 V8 H16" fill="none" stroke="{B}" stroke-width="1.8"/><path d="M8 20 V12 H16" fill="none" stroke="{O}" stroke-width="1.5" stroke-dasharray="2 1.4"/>',
    "project": f'<path d="M3 16 L10 20 L21 14 L14 10 Z" fill="{B}" opacity=".3" stroke="{B}"/><path d="M12 3 V14" stroke="{O}" stroke-width="1.6"/><path d="M9 11 L12 14 L15 11" stroke="{O}" stroke-width="1.6" fill="none"/>',
    "mirror_sketch": f'<path d="M12 2 V22" stroke="{O}" stroke-dasharray="2 1.5"/><path d="M4 6 L9 18" stroke="{B}" stroke-width="1.8"/><path d="M20 6 L15 18" stroke="{B}" stroke-width="1.8" opacity=".6"/>',
    "construction": f'<path d="M4 20 L20 4" stroke="{O}" stroke-width="2" stroke-dasharray="3 2"/>',
    "dimension": f'<path d="M4 8 V20 M20 8 V20 M4 12 H20 M4 12 L7 10 M4 12 L7 14 M20 12 L17 10 M20 12 L17 14" stroke="{D}" stroke-width="1.3" fill="none"/>'
                 f'<text x="12" y="9" font-size="7" text-anchor="middle" fill="{B}" font-family="sans-serif">20</text>',
    "c_coincident": f'<circle cx="12" cy="12" r="3" fill="{D}"/><path d="M3 12 H21" stroke="{B}" stroke-width="1.4"/>',
    "c_horizontal": f'<path d="M3 12 H21" stroke="{B}" stroke-width="2"/><text x="12" y="9" font-size="8" text-anchor="middle" fill="{D}" font-family="sans-serif">H</text>',
    "c_vertical": f'<path d="M12 3 V21" stroke="{B}" stroke-width="2"/><text x="17" y="14" font-size="8" text-anchor="middle" fill="{D}" font-family="sans-serif">V</text>',
    "c_parallel": f'<path d="M5 19 L13 5 M11 19 L19 5" stroke="{B}" stroke-width="2"/>',
    "c_perpendicular": f'<path d="M5 19 H19 M12 19 V5" stroke="{B}" stroke-width="2"/>',
    "c_tangent": f'<circle cx="12" cy="14" r="6" fill="none" stroke="{B}" stroke-width="1.6"/><path d="M3 8 H21" stroke="{D}" stroke-width="1.6"/>',
    "c_equal": f'<path d="M5 9 H19 M5 15 H19" stroke="{B}" stroke-width="2"/>',
    "c_concentric": f'<circle cx="12" cy="12" r="8" fill="none" stroke="{B}" stroke-width="1.5"/><circle cx="12" cy="12" r="4" fill="none" stroke="{B}" stroke-width="1.5"/>',
    "c_midpoint": f'<path d="M3 16 H21" stroke="{B}" stroke-width="1.8"/><path d="M12 9 L15 14 H9 Z" fill="{D}"/>',
    "c_symmetric": f'<path d="M12 3 V21" stroke="{O}" stroke-dasharray="2 1.5"/><circle cx="6" cy="12" r="2.2" fill="{B}"/><circle cx="18" cy="12" r="2.2" fill="{B}"/>',
    "c_fix": f'<rect x="6" y="11" width="12" height="9" rx="1" fill="{O}"/><path d="M8.5 11 V8 A3.5 3.5 0 0 1 15.5 8 V11" fill="none" stroke="{D}" stroke-width="1.6"/>',
    "c_collinear": f'<path d="M3 16 L9 12 M13 9.5 L21 4.5" stroke="{B}" stroke-width="2"/>',
    "ellipse": f'<ellipse cx="12" cy="12" rx="10" ry="6" fill="none" stroke="{B}" stroke-width="1.8" transform="rotate(-20 12 12)"/><circle cx="12" cy="12" r="1.5" fill="{D}"/>',
    "text": f'<text x="12" y="19" font-size="19" font-weight="bold" text-anchor="middle" fill="{B}" font-family="serif">A</text>',
    "extend": f'<path d="M3 16 H14" stroke="{B}" stroke-width="1.8"/><path d="M14 16 H20" stroke="{O}" stroke-width="1.8" stroke-dasharray="2 1.5"/><path d="M21 4 V20" stroke="{D}" stroke-width="1.8"/>',
    "rib": f'<path d="M3 20 H21 V16 H3 Z" {_BODY}/><path d="M9 16 V6 H12 V16" {_BODY}/>',
    "thread": f'<path d="M7 3 H17 V21 H7 Z" {_BODY}/><path d="M7 7 L17 9 M7 11 L17 13 M7 15 L17 17" stroke="{D}" stroke-width="1.2"/>',
    "import2d": f'<path d="M4 4 H14 L19 9 V20 H4 Z" fill="white" stroke="{D}"/><path d="M7 15 L11 9 L15 15 Z" fill="none" stroke="{B}" stroke-width="1.5"/>',
    "dxf": f'<path d="M4 4 H14 L19 9 V20 H4 Z" fill="white" stroke="{D}"/><text x="11.5" y="17" font-size="6" text-anchor="middle" fill="{GR}" font-family="sans-serif" font-weight="bold">DXF</text>',
    "measure": f'<path d="M3 17 L17 3 L21 7 L7 21 Z" fill="#f2d16b" stroke="{D}"/><path d="M7 13 L9 15 M10 10 L12 12 M13 7 L15 9" stroke="{D}"/>',
    "section": f'<path d="M3 8 L12 4 L21 8 V16 L12 20 L3 16 Z" {_BODY}/><path d="M3 12 L12 8 L21 12 L12 16 Z" fill="{O}" opacity=".6"/>',
    "mass": f'<path d="M6 9 H18 L20 20 H4 Z" fill="{G}" stroke="{D}"/><circle cx="12" cy="6" r="2.5" fill="none" stroke="{D}" stroke-width="1.5"/>',
    "parameters": f'<text x="12" y="17" font-size="13" text-anchor="middle" fill="{B}" font-family="serif" font-style="italic">fx</text>',
    "undo": f'<path d="M9 7 H15 A5 5 0 0 1 15 17 H8" fill="none" stroke="{D}" stroke-width="1.8"/><path d="M10 3 L5 7 L10 11" fill="none" stroke="{D}" stroke-width="1.8"/>',
    "redo": f'<path d="M15 7 H9 A5 5 0 0 0 9 17 H16" fill="none" stroke="{D}" stroke-width="1.8"/><path d="M14 3 L19 7 L14 11" fill="none" stroke="{D}" stroke-width="1.8"/>',
    "new": f'<path d="M5 3 H14 L19 8 V21 H5 Z" fill="white" stroke="{D}"/><path d="M14 3 V8 H19" fill="none" stroke="{D}"/>',
    "open": f'<path d="M3 6 H9 L11 8 H20 V19 H3 Z" fill="#f2d16b" stroke="{D}"/>',
    "save": f'<path d="M4 4 H17 L20 7 V20 H4 Z" fill="{B}" stroke="{D}"/><rect x="7" y="4" width="9" height="6" fill="white"/><rect x="7" y="13" width="10" height="7" fill="#dfe8f5"/>',
    "orbit": f'<ellipse cx="12" cy="12" rx="9" ry="4" fill="none" stroke="{D}" stroke-width="1.5"/><path d="M19 9 L21 12 L17.5 12.5" fill="none" stroke="{D}" stroke-width="1.5"/>',
    "pan": f'<path d="M12 3 V21 M3 12 H21" stroke="{D}" stroke-width="1.5"/><path d="M9 6 L12 3 L15 6 M9 18 L12 21 L15 18 M6 9 L3 12 L6 15 M18 9 L21 12 L18 15" fill="none" stroke="{D}" stroke-width="1.5"/>',
    "zoom": f'<circle cx="10" cy="10" r="6" fill="none" stroke="{D}" stroke-width="1.8"/><path d="M14.5 14.5 L20 20" stroke="{D}" stroke-width="2.2"/>',
    "fit": f'<path d="M3 8 V3 H8 M16 3 H21 V8 M21 16 V21 H16 M8 21 H3 V16" fill="none" stroke="{D}" stroke-width="1.6"/><rect x="8" y="8" width="8" height="8" fill="{S}" stroke="{D}"/>',
    "display": f'<path d="M3 8 L12 4 L21 8 V16 L12 20 L3 16 Z" {_BODY}/>',
    "grid": "".join(f'<path d="M{v} 3 V21 M3 {v} H21" stroke="{G}" stroke-width="1"/>' for v in (6, 12, 18)),
    "eye": f'<path d="M2 12 Q12 3 22 12 Q12 21 2 12 Z" fill="none" stroke="{D}" stroke-width="1.4"/><circle cx="12" cy="12" r="3.5" fill="{D}"/>',
    "eye_off": f'<path d="M2 12 Q12 3 22 12 Q12 21 2 12 Z" fill="none" stroke="{G}" stroke-width="1.2" opacity=".6"/><path d="M4 20 L20 4" stroke="{G}" stroke-width="1.4"/>',
    "body": f'<path d="M3 8 L12 4 L21 8 V16 L12 20 L3 16 Z" {_BODY}/><path d="M3 8 L12 12 L21 8 M12 12 V20" stroke="{D}" fill="none" stroke-width=".8"/>',
    "folder": f'<path d="M3 6 H9 L11 8 H20 V19 H3 Z" fill="#c9d3e0" stroke="{G}"/>',
    "origin": f'<circle cx="12" cy="12" r="2.5" fill="{D}"/><path d="M12 12 H21" stroke="{R}" stroke-width="1.6"/><path d="M12 12 V3" stroke="{GR}" stroke-width="1.6"/><path d="M12 12 L5 19" stroke="{B}" stroke-width="1.6"/>',
    "warning": f'<path d="M12 3 L22 20 H2 Z" fill="#f2c94c" stroke="{D}"/><path d="M12 9 V14" stroke="{D}" stroke-width="2"/><circle cx="12" cy="17" r="1.2" fill="{D}"/>',
    "error": f'<circle cx="12" cy="12" r="9" fill="{R}"/><path d="M8 8 L16 16 M16 8 L8 16" stroke="white" stroke-width="2"/>',
    "play_first": f'<path d="M5 4 V20 M19 4 L8 12 L19 20 Z" fill="{D}" stroke="{D}" stroke-width="1.5"/>',
    "play_prev": f'<path d="M17 4 L6 12 L17 20 Z" fill="{D}"/>',
    "play_next": f'<path d="M7 4 L18 12 L7 20 Z" fill="{D}"/>',
    "play_last": f'<path d="M19 4 V20 M5 4 L16 12 L5 20 Z" fill="{D}" stroke="{D}" stroke-width="1.5"/>',
    "search": f'<circle cx="10" cy="10" r="6" fill="none" stroke="{D}" stroke-width="1.8"/><path d="M14.5 14.5 L20 20" stroke="{D}" stroke-width="2.2"/>',
    "appearance": f'<circle cx="12" cy="12" r="9" fill="#e9eef5" stroke="{D}"/><circle cx="8" cy="9" r="2" fill="{R}"/><circle cx="13" cy="7" r="2" fill="{GR}"/><circle cx="16.5" cy="11" r="2" fill="{B}"/>',
    "interference": f'<rect x="3" y="7" width="11" height="11" {_BODY}/><rect x="10" y="4" width="11" height="11" {_BODY} opacity=".85"/><rect x="10" y="7" width="4" height="8" fill="{R}"/>',
}


@lru_cache(maxsize=None)
def _render(name: str, size: int, disabled: bool) -> QPixmap:
    body = ICONS.get(name, ICONS["box"])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">{body}</svg>'
    r = QSvgRenderer(QByteArray(svg.encode()))
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    if disabled:
        p.setOpacity(0.35)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


def icon(name: str) -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64):
        ic.addPixmap(_render(name, s, False), QIcon.Normal)
        ic.addPixmap(_render(name, s, True), QIcon.Disabled)
    return ic


def pixmap(name: str, size: int = 24) -> QPixmap:
    return _render(name, size, False)
