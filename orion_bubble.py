#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  ORION VOICE OVERLAY — SLEEK COMPACT DESKTOP BUBBLE
═══════════════════════════════════════════════════════════════════════════════
- Matches the official website branding:
    * Iconic 4-point star with stardust accents
    * Authentic stylized "ORION" lettering with constellation bow/arrow terminal
- Sleek, compact footprint (236 x 46 px) — fits neatly under the browser/tab bar
- NO muddy smoky aura / NO banding edges: 100% clean alpha glass with crisp laser rim
- Smooth live microphone audio reactivity (or simulated ambient speech wave fallback)
- Drag anywhere with mouse | Press ESC to close
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import math
import numpy as np

try:
    import sounddevice as sd
except Exception as _sd_err:
    sd = None
    print(f"[Orion] sounddevice unavailable ({_sd_err}). Falling back to simulated audio.")

from PyQt6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QPixmap, QPolygonF
)
from PyQt6.QtWidgets import QApplication, QWidget

# ═════════════════════════════════════════════════════════════════════════════
#  COMPACT DIMENSIONS & STYLING
# ═════════════════════════════════════════════════════════════════════════════
BUBBLE_W = 236             # Compact width (sits neatly at top of screen)
BUBBLE_H = 46              # Compact height
BUBBLE_R = 23.0            # Full stadium / capsule rounded ends
MARGIN = 8                 # Tight margin (no oversized glow box)
WIN_W = BUBBLE_W + 2 * MARGIN
WIN_H = BUBBLE_H + 2 * MARGIN
TOP_OFFSET = 8             # Pixels from screen top

CODE_RED = QColor(227, 27, 35)      # Primary Orion Crimson
BRIGHT_RED = QColor(255, 45, 65)    # Neon accent
WHITE = QColor(255, 255, 255)
DARK_BG = QColor(10, 12, 18, 238)   # Clean premium dark glass (solid opacity, no muddy gradient)


# ═════════════════════════════════════════════════════════════════════════════
#  WEBSITE LOGO VECTOR ENGINE (Exact "ORION" + Star + Constellation Bow/Arrow)
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


def _star_path(cx, cy, r_outer, r_inner):
    """4-pointed star matching the website logo."""
    p = QPainterPath()
    p.moveTo(cx, cy - r_outer)
    p.lineTo(cx + r_inner, cy - r_inner)
    p.lineTo(cx + r_outer, cy)
    p.lineTo(cx + r_inner, cy + r_inner)
    p.lineTo(cx, cy + r_outer)
    p.lineTo(cx - r_inner, cy + r_inner)
    p.lineTo(cx - r_outer, cy)
    p.lineTo(cx - r_inner, cy - r_inner)
    p.closeSubpath()
    return p


def build_website_orion_pixmap(dpr=2.0):
    """
    Renders the exact website ORION branding:
    - 4-point star with red border & white core
    - Stardust speck trail
    - Stylized ORION font with hunter bow/arrow motif on the 'N'
    """
    canvas_w, canvas_h = 132, 28
    pm = QPixmap(int(canvas_w * dpr), int(canvas_h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    cy = canvas_h / 2.0

    # 1. THE 4-POINT STAR (website icon)
    star_cx = 10.0
    star_cy = cy

    # Red outer spark
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(CODE_RED))
    p.drawPath(_star_path(star_cx, star_cy, 9.5, 2.5))

    # White inner diamond
    p.setBrush(QBrush(WHITE))
    p.drawPath(_star_path(star_cx, star_cy, 5.5, 1.4))

    # Stardust specks trailing toward the 'O'
    p.setBrush(QBrush(WHITE))
    p.drawEllipse(QPointF(19.0, cy - 4.5), 0.9, 0.9)
    p.drawEllipse(QPointF(22.0, cy - 2.0), 1.2, 1.2)
    p.drawEllipse(QPointF(20.5, cy + 3.0), 0.8, 0.8)
    p.drawEllipse(QPointF(24.5, cy + 1.5), 1.0, 1.0)

    # 2. "ORION" LETTERING (White bold sci-fi geometric vectors)
    p.setBrush(QBrush(WHITE))
    p.setPen(Qt.PenStyle.NoPen)

    t = 3.2  # Stroke thickness
    H = 16.0 # Cap height
    top_y = cy - H / 2.0
    bot_y = cy + H / 2.0

    # Letter 'O' (ring with top notch break like website)
    ox = 30.0
    o_outer = _circle(ox + 8, cy, 8.0)
    o_inner = _circle(ox + 8, cy, 8.0 - t)
    o_path = o_outer.subtracted(o_inner)
    o_notch = _rect(ox + 6.6, top_y - 1, 2.8, 4.0)
    p.drawPath(o_path.subtracted(o_notch))

    # Letter 'R'
    rx = ox + 19.5
    r_stem = _rect(rx, top_y, t, H)
    r_bowl_out = _circle(rx + 6.0, top_y + 4.5, 4.8)
    r_bowl_in = _circle(rx + 6.0, top_y + 4.5, 4.8 - t)
    r_bowl = r_bowl_out.subtracted(r_bowl_in)
    r_leg = _poly([(rx + 2.0, top_y + 8.0), (rx + 5.0, top_y + 8.0),
                   (rx + 11.5, bot_y), (rx + 8.0, bot_y)])
    p.drawPath(r_stem.united(r_bowl).united(r_leg))

    # Letter 'I'
    ix = rx + 15.0
    p.drawPath(_rect(ix, top_y, t, H))

    # Second 'O'
    o2x = ix + 7.5
    o2_outer = _circle(o2x + 8, cy, 8.0)
    o2_inner = _circle(o2x + 8, cy, 8.0 - t)
    p.drawPath(o2_outer.subtracted(o2_inner))

    # Letter 'N' with Orion Hunter Bow/Arrow terminal
    nx = o2x + 19.5
    n_w = 12.0
    n_left = _rect(nx, top_y, t, H)
    n_diag = _poly([(nx, top_y), (nx + t, top_y),
                    (nx + n_w, bot_y), (nx + n_w - t, bot_y)])
    n_right = _rect(nx + n_w - t, top_y, t, H)
    p.drawPath(n_left.united(n_diag).united(n_right))

    # Constellation bow/arrow barb on the right of N (from the website logo)
    bow_pts = [
        (nx + n_w + 1.0, top_y + 4.0),
        (nx + n_w + 4.5, cy),
        (nx + n_w + 1.0, bot_y - 4.0),
        (nx + n_w + 2.6, cy)
    ]
    p.drawPath(_poly(bow_pts))

    p.end()
    return pm


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(WIN_W, WIN_H)

        # Center at top of screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width() - WIN_W) // 2, screen.y() + TOP_OFFSET)

        # Mouse drag tracking
        self.drag_position = QPoint()

        # Render website ORION vector branding once (crisp, cached at Retina DPI)
        dpr = max(2.0, self.devicePixelRatioF())
        self.brand_pixmap = build_website_orion_pixmap(dpr)

        # 6 audio bars on left, 6 on right (compact and sleek)
        self.num_bars = 6
        self.audio_levels = np.zeros(self.num_bars)
        self.sim_step = 0.0

        # Live microphone audio stream
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
                print("[Orion] Live microphone connected.")
            except Exception as e:
                print(f"[Orion] Mic connection note ({e}). Using simulated wave.")
                self.has_mic = False

        # 60 FPS update timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def _audio_callback(self, indata, frames, time, status):
        if indata.size > 0:
            fft_vals = np.abs(np.fft.rfft(indata[:, 0]))[:self.num_bars]
            norm_vals = np.clip(fft_vals / 14.0, 0.0, 1.0)
            self.audio_levels = self.audio_levels * 0.45 + norm_vals * 0.55

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        badge_rect = QRectF(cx - BUBBLE_W / 2.0, cy - BUBBLE_H / 2.0, BUBBLE_W, BUBBLE_H)

        # 1. CRISP SOLID GLASS CAPSULE (No smoky red aura, clean cut)
        painter.setPen(QPen(CODE_RED, 1.6))
        painter.setBrush(QBrush(DARK_BG))
        painter.drawRoundedRect(badge_rect, BUBBLE_R, BUBBLE_R)

        # 2. SUBTLE INNER LASER ACCENTS (Top and bottom notches)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(CODE_RED))
        notch_w = 26.0
        top_y = cy - BUBBLE_H / 2.0
        bot_y = cy + BUBBLE_H / 2.0 - 2.5
        painter.drawRoundedRect(QRectF(cx - 50, top_y, notch_w, 2.5), 1, 1)
        painter.drawRoundedRect(QRectF(cx + 24, top_y, notch_w, 2.5), 1, 1)
        painter.drawRoundedRect(QRectF(cx - 36, bot_y, notch_w, 2.5), 1, 1)
        painter.drawRoundedRect(QRectF(cx + 10, bot_y, notch_w, 2.5), 1, 1)

        # 3. WEBSITE "ORION" BRANDING (Star + Stardust + Stylized ORION)
        pm_w = self.brand_pixmap.width() / self.brand_pixmap.devicePixelRatio()
        pm_h = self.brand_pixmap.height() / self.brand_pixmap.devicePixelRatio()
        painter.drawPixmap(QPointF(cx - pm_w / 2.0, cy - pm_h / 2.0), self.brand_pixmap)

        # 4. SLEEK EQUALIZER BARS (Flanking left & right inside the capsule)
        if not self.has_mic:
            self.sim_step += 0.08

        bars = []
        for i in range(self.num_bars):
            if self.has_mic:
                bars.append(float(self.audio_levels[i]))
            else:
                val = (math.sin(self.sim_step + i * 0.5) * 0.35 +
                       math.cos(self.sim_step * 1.6 - i * 0.4) * 0.25 + 0.35)
                bars.append(max(0.12, min(1.0, val)))

        bar_spacing = 5.2
        max_h = 22.0

        # Left Bars (Tapering toward outer left curve)
        left_start_x = cx - 74.0
        for i in range(self.num_bars):
            val = bars[self.num_bars - 1 - i]
            taper = 0.35 + 0.65 * ((i + 1) / self.num_bars)
            h = max(4.0, val * max_h * taper)
            bx = left_start_x - (self.num_bars - 1 - i) * bar_spacing
            col = WHITE if i == self.num_bars - 1 else BRIGHT_RED
            p = QPen(col, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(p)
            painter.drawLine(QPointF(bx, cy - h / 2.0), QPointF(bx, cy + h / 2.0))

        # Right Bars (Tapering toward outer right curve)
        right_start_x = cx + 74.0
        for i in range(self.num_bars):
            val = bars[i]
            taper = 0.35 + 0.65 * ((self.num_bars - i) / self.num_bars)
            h = max(4.0, val * max_h * taper)
            bx = right_start_x + i * bar_spacing
            col = WHITE if i == 0 else BRIGHT_RED
            p = QPen(col, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(p)
            painter.drawLine(QPointF(bx, cy - h / 2.0), QPointF(bx, cy + h / 2.0))

    # Click & drag anywhere on the bubble
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    # Escape to close
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
    print("[Orion] Overlay launched! Drag to position. Press ESC to close.")
    sys.exit(app.exec())