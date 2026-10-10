import sys
import math
import numpy as np

try:
    import sounddevice as sd
except Exception as _sd_err:          # PortAudio missing etc. -> simulated wave fallback
    sd = None
    print(f"[Orion] sounddevice unavailable ({_sd_err}). Falling back to simulated wave.")

from PyQt6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PyQt6.QtWidgets import QApplication, QWidget


# ═════════════════════════════════════════════════════════════════════════════
#  LAYOUT
# ═════════════════════════════════════════════════════════════════════════════
BADGE_W, BADGE_H, BADGE_R = 200, 58, 18   # rounded-rectangle bubble
MARGIN = 36                               # room around the badge for the sound bars
WIN_W, WIN_H = BADGE_W + 2 * MARGIN, BADGE_H + 2 * MARGIN
TOP_OFFSET = 6                            # gap between screen top and the window

CODE_RED = QColor(227, 27, 35)
WHITE = QColor(255, 255, 255)


# ═════════════════════════════════════════════════════════════════════════════
#  BRANDING  (pure vector geometry - no system fonts, identical on every OS)
# ═════════════════════════════════════════════════════════════════════════════
def _rect(x, y, w, h):
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


def _circle(cx, cy, r):
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _poly(pts):
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    p.closeSubpath()
    return p


# ORION lettering: angular sci-fi geometric letters (cap height = 100 units)
_t = 17  # stroke thickness


def _o_O():
    return _circle(50, 50, 50).subtracted(_circle(50, 50, 50 - _t)), 100


def _o_R():
    outer = _rect(0, 0, 40, 58).united(_circle(40, 29, 29))
    inner = _rect(_t, _t, 40 - _t, 58 - 2 * _t).united(_circle(40, 29, 29 - _t))
    p = outer.subtracted(inner).united(_rect(0, 0, _t, 100))
    p = p.united(_poly([(32, 58), (54, 58), (82, 100), (60, 100)]))
    return p, 82


def _o_I():
    return _rect(0, 0, _t, 100), _t


def _o_N():
    w = 76
    p = _rect(0, 0, _t, 100).united(_rect(w - _t, 0, _t, 100))
    p = p.united(_poly([(0, 0), (_t + 6, 0), (w, 100), (w - _t - 6, 100)]))
    return p, w


def _orion_paths():
    gap = 15
    paths, x = [], 0.0
    for path, w in [_o_O(), _o_R(), _o_I(), _o_O(), _o_N()]:
        paths.append(QTransform().translate(x, 0).map(path))
        x += w + gap
    return paths


_ORION_LETTERS = _orion_paths()
_ORION_BOUNDS = QPainterPath()
for _g in _ORION_LETTERS:
    _ORION_BOUNDS.addPath(_g)
_ORION_BOUNDS = _ORION_BOUNDS.boundingRect()


def _star_path(cx, cy, R):
    """Multi-point spark: 4 long rays + 4 short diagonal rays."""
    pts = []
    for k in range(8):
        a_out = math.radians(k * 45 - 90)
        r_out = R if k % 2 == 0 else R * 0.55
        pts.append((cx + math.cos(a_out) * r_out, cy + math.sin(a_out) * r_out))
        a_in = math.radians(k * 45 + 22.5 - 90)
        pts.append((cx + math.cos(a_in) * R * 0.26, cy + math.sin(a_in) * R * 0.26))
    return _poly(pts)


BRAND_W, BRAND_H = 160, 48     # cached content pixmap (star + ORION), logical px
STAR_R = 15                    # star radius
TEXT_H = 24                    # ORION cap height
STAR_GAP = 11                  # space between star and text


def build_brand_pixmap(dpr):
    """Pre-renders star + ORION text once at device resolution (crisp, cheap at 60 FPS)."""
    pm = QPixmap(int(BRAND_W * dpr), int(BRAND_H * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    s = TEXT_H / _ORION_BOUNDS.height()
    text_w = _ORION_BOUNDS.width() * s
    total = STAR_R * 2 + STAR_GAP + text_w
    x0 = (BRAND_W - total) / 2.0
    cy = BRAND_H / 2.0

    # Red spark with a white core
    sx = x0 + STAR_R
    p.setBrush(QBrush(CODE_RED))
    p.drawPath(_star_path(sx, cy, STAR_R))
    p.setBrush(QBrush(WHITE))
    p.drawPath(_star_path(sx, cy, STAR_R * 0.5))

    # ORION lettering (red)
    p.save()
    p.translate(x0 + STAR_R * 2 + STAR_GAP, cy)
    p.scale(s, s)
    p.translate(-_ORION_BOUNDS.left(), -_ORION_BOUNDS.center().y())
    p.setBrush(QBrush(CODE_RED))
    for g in _ORION_LETTERS:
        p.drawPath(g)
    p.restore()

    p.end()
    return pm


# ═════════════════════════════════════════════════════════════════════════════
#  ROUNDED-RECTANGLE PERIMETER SAMPLING (for the sound bars)
# ═════════════════════════════════════════════════════════════════════════════
def _perimeter_samples(cx, cy, w, h, r, n, inset=2.0):
    """n evenly spaced points around a rounded rect, clockwise from top-centre.
    Returns arrays (x, y, nx, ny): start point (inset px outside the edge) and outward normal."""
    hw, hh = w / 2.0, h / 2.0
    segs = [
        ("line", (cx, cy - hh), (cx + hw - r, cy - hh), (0, -1)),
        ("arc", (cx + hw - r, cy - hh + r), -90, 0),
        ("line", (cx + hw, cy - hh + r), (cx + hw, cy + hh - r), (1, 0)),
        ("arc", (cx + hw - r, cy + hh - r), 0, 90),
        ("line", (cx + hw - r, cy + hh), (cx - hw + r, cy + hh), (0, 1)),
        ("arc", (cx - hw + r, cy + hh - r), 90, 180),
        ("line", (cx - hw, cy + hh - r), (cx - hw, cy - hh + r), (-1, 0)),
        ("arc", (cx - hw + r, cy - hh + r), 180, 270),
        ("line", (cx - hw + r, cy - hh), (cx, cy - hh), (0, -1)),
    ]
    lengths = []
    for sg in segs:
        if sg[0] == "line":
            lengths.append(math.hypot(sg[2][0] - sg[1][0], sg[2][1] - sg[1][1]))
        else:
            lengths.append(math.radians(sg[3] - sg[2]) * r)
    total = sum(lengths)

    out = []
    for i in range(n):
        d = i * total / n
        for sg, L in zip(segs, lengths):
            if d <= L or sg is segs[-1]:
                t = 0.0 if L == 0 else min(d / L, 1.0)
                if sg[0] == "line":
                    x = sg[1][0] + (sg[2][0] - sg[1][0]) * t
                    y = sg[1][1] + (sg[2][1] - sg[1][1]) * t
                    nx, ny = sg[3]
                else:
                    th = math.radians(sg[2] + (sg[3] - sg[2]) * t)
                    nx, ny = math.cos(th), math.sin(th)
                    x, y = sg[1][0] + nx * r, sg[1][1] + ny * r
                out.append((x + nx * inset, y + ny * inset, nx, ny))
                break
            d -= L
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  OVERLAY WINDOW
# ═════════════════════════════════════════════════════════════════════════════
class OrionDesktopBubble(QWidget):
    def __init__(self):
        super().__init__()

        # Frameless, Always-on-Top, Transparent Desktop Overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # so ESC works after a click
        self.resize(WIN_W, WIN_H)

        # Top-centre of the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - WIN_W) // 2, screen.y() + TOP_OFFSET)

        # Drag tracking
        self.drag_position = QPoint()

        # Cached vector branding (rendered once, at >= 2x for crisp edges)
        self.brand_pixmap = build_brand_pixmap(max(2.0, self.devicePixelRatioF()))

        # Audio frequency array
        self.num_bars = 40
        self.audio_levels = np.zeros(self.num_bars)
        self.sim_step = 0

        # Bar anchor points around the rounded rectangle
        self.bar_points = _perimeter_samples(
            WIN_W / 2.0, WIN_H / 2.0, BADGE_W, BADGE_H, BADGE_R, self.num_bars)

        # Start live microphone audio stream
        self.stream = None
        self.has_mic = False
        if sd is not None:
            try:
                self.stream = sd.InputStream(
                    channels=1,
                    samplerate=44100,
                    blocksize=1024,
                    callback=self._audio_callback
                )
                self.stream.start()
                self.has_mic = True
            except Exception as e:
                print(f"[Orion] Mic connection note ({e}). Falling back to simulated wave.")
                self.has_mic = False

        # 60 FPS Render Loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def _audio_callback(self, indata, frames, time, status):
        if indata.size > 0:
            # FFT frequency analysis for reactive bars
            fft_vals = np.abs(np.fft.rfft(indata[:, 0]))[:self.num_bars]
            norm_vals = np.clip(fft_vals / 12.0, 0, 1)
            # Smooth transition
            self.audio_levels = self.audio_levels * 0.4 + norm_vals * 0.6

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        # 1. Dark Glass Rounded-Rectangle Background
        painter.setBrush(QBrush(QColor(10, 15, 30, 210)))  # Semi-transparent dark slate
        pen = QPen(QColor(227, 27, 35, 120))               # Red glow outline
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(cx - BADGE_W / 2.0, cy - BADGE_H / 2.0, BADGE_W, BADGE_H),
                                BADGE_R, BADGE_R)

        # 2. Dynamic Sound Bars around the rectangle
        if not self.has_mic:
            self.sim_step += 0.06

        for i, (x_start, y_start, nx, ny) in enumerate(self.bar_points):
            if self.has_mic:
                level = self.audio_levels[i % len(self.audio_levels)]
                bar_len = level * 26 + 3
            else:
                bar_len = math.sin(self.sim_step + i * 0.3) * 8 + 11

            # Alternate CodeRED Red and Glowing White
            color = QColor(227, 27, 35) if i % 2 == 0 else QColor(255, 255, 255)
            bar_pen = QPen(color)
            bar_pen.setWidth(3)
            bar_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(bar_pen)
            painter.drawLine(QPointF(x_start, y_start),
                             QPointF(x_start + nx * bar_len, y_start + ny * bar_len))

        # 3. Star + ORION (cached vector pixmap)
        painter.drawPixmap(QPointF(cx - BRAND_W / 2.0, cy - BRAND_H / 2.0), self.brand_pixmap)

    # Click & Drag Windows Support
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    # Escape to Exit
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    bubble = OrionDesktopBubble()
    bubble.show()
    bubble.activateWindow()
    print("[Orion] Bubble launched! Click and drag to move it. Press ESC to close.")
    sys.exit(app.exec())
