import sys
import math
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QApplication, QWidget

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
        self.resize(380, 380)

        # Center on primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 380) // 2, (screen.height() - 380) // 2)

        # Drag tracking
        self.drag_position = QPoint()

        # Audio frequency array
        self.num_bars = 40
        self.audio_levels = np.zeros(self.num_bars)
        self.sim_step = 0

        # Start live microphone audio stream
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

        center_x = self.width() // 2
        center_y = self.height() // 2
        inner_radius = 100

        # 1. Dark Glass Circle Background
        painter.setBrush(QBrush(QColor(10, 15, 30, 210)))  # Semi-transparent dark slate
        pen = QPen(QColor(227, 27, 35, 120))               # Red glow outline
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(center_x - inner_radius, center_y - inner_radius, inner_radius * 2, inner_radius * 2)

        # 2. Dynamic Radial Sound Waves
        if not self.has_mic:
            self.sim_step += 0.06

        for i in range(self.num_bars):
            if self.has_mic:
                level = self.audio_levels[i % len(self.audio_levels)]
                bar_len = level * 42 + 4
            else:
                bar_len = math.sin(self.sim_step + i * 0.3) * 14 + 18

            angle = (i * 2 * math.pi) / self.num_bars
            x_start = center_x + math.cos(angle) * (inner_radius + 2)
            y_start = center_y + math.sin(angle) * (inner_radius + 2)
            x_end = center_x + math.cos(angle) * (inner_radius + 2 + bar_len)
            y_end = center_y + math.sin(angle) * (inner_radius + 2 + bar_len)

            # Alternate CodeRED Red and Glowing White
            color = QColor(227, 27, 35) if i % 2 == 0 else QColor(255, 255, 255)
            pen = QPen(color)
            pen.setWidth(3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(x_start), int(y_start), int(x_end), int(y_end))

        # 3. Orion Star & Text Branding
        # Star Accent
        painter.setPen(QPen(QColor(227, 27, 35)))
        star_font = QFont("Arial", 18, QFont.Weight.Bold)
        painter.setFont(star_font)
        painter.drawText(center_x - 15, center_y - 28, 30, 30, Qt.AlignmentFlag.AlignCenter, "✦")

        # ORION Label
        painter.setPen(QPen(QColor(255, 255, 255)))
        text_font = QFont("Segoe UI", 16, QFont.Weight.ExtraBold)
        text_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5)
        painter.setFont(text_font)
        painter.drawText(center_x - 100, center_y - 8, 200, 30, Qt.AlignmentFlag.AlignCenter, "ORION")

        # CodeRED Badge Subtext
        painter.setPen(QPen(QColor(227, 27, 35)))
        sub_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(sub_font)
        painter.drawText(center_x - 60, center_y + 22, 120, 20, Qt.AlignmentFlag.AlignCenter, "CODERED")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bubble = OrionDesktopBubble()
    bubble.show()
    print("[Orion] Bubble launched! Click and drag to move it. Press ESC to close.")
    sys.exit(app.exec())