"""One-off generator for the app icon (run manually, not at app runtime).

Two arrows chasing each other round a circle: the app turns one format into
another. Drawn with QPainter rather than PIL so icon generation needs nothing
the app does not already depend on, and each size is rendered natively instead
of downsampled from one master, which keeps the stroke crisp at 16px.

    python assets/make_icon.py
"""

import math
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

ASSETS = Path(__file__).resolve().parent
ICONSET = ASSETS / "icon.iconset"

TEAL_TOP = QColor("#1FB6A8")
INDIGO_BOTTOM = QColor("#1B4E9B")
WHITE = QColor("#FFFFFF")

SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}

# Each arrow is one arc plus a head. Both arcs start where the other one's head
# ends, which is what makes the pair read as a single cycle.
ARC_SPAN = 140  # degrees
ARC_STARTS = (110, 290)


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, TEAL_TOP)
    gradient.setColorAt(1.0, INDIGO_BOTTOM)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    painter.fillPath(tile, QBrush(gradient))

    centre = size / 2
    radius = size * 0.26
    stroke = max(1.5, size * 0.085)

    pen = QPen(WHITE, stroke)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    box = QRectF(centre - radius, centre - radius, radius * 2, radius * 2)
    for start in ARC_STARTS:
        # Qt measures arc angles in sixteenths of a degree, counter-clockwise.
        painter.drawArc(box, start * 16, ARC_SPAN * 16)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(WHITE)
    for start in ARC_STARTS:
        painter.drawPolygon(_arrow_head(centre, radius, size, start + ARC_SPAN))

    painter.end()
    return image


def _arrow_head(centre: float, radius: float, size: float, angle_deg: float) -> QPolygonF:
    """A triangle at ``angle_deg`` on the circle, pointing the way the arc runs.

    Screen y grows downward, so the point on the circle is (cos, -sin); the
    tangent for an increasing (counter-clockwise) angle is (-sin, -cos).
    """
    angle = math.radians(angle_deg)
    tip_x = centre + radius * math.cos(angle)
    tip_y = centre - radius * math.sin(angle)

    dx, dy = -math.sin(angle), -math.cos(angle)
    nx, ny = -dy, dx

    length = size * 0.15
    half_width = size * 0.105

    tip = QPointF(tip_x + dx * length, tip_y + dy * length)
    back_x = tip_x - dx * length * 0.35
    back_y = tip_y - dy * length * 0.35
    left = QPointF(back_x + nx * half_width, back_y + ny * half_width)
    right = QPointF(back_x - nx * half_width, back_y - ny * half_width)
    return QPolygonF([tip, left, right])


def main() -> int:
    QGuiApplication([])  # QImage/QPainter need an application instance.
    ICONSET.mkdir(exist_ok=True)

    for name, px in SIZES.items():
        if not draw_icon(px).save(str(ICONSET / name)):
            print(f"Failed to write {name}", file=sys.stderr)
            return 1

    icns = ASSETS / "icon.icns"
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(f"Wrote {len(SIZES)} PNGs to {ICONSET}")
    print(f"Wrote {icns} ({icns.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
