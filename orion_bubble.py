import sys
import math
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QWidget

# --- Audio Configuration ---
SAMPLE_RATE = 44100
CHUNK_SIZE = 1024
NUM_BARS_PER_SIDE = 15
NOISE_GATE = 0.012

class OrionVoiceBubble(QWidget):
    def __init__(self):
        super().__init__()

        # Window Dimensions (Capsule HUD)
        self.bubble_width = 380
        self.bubble_height = 86
        self.setFixedSize(self.bubble_width, self.bubble_height)

        # Frameless, transparent, always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Center top position under webcam notch
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.bubble_width) // 2
        y = 20
        self.move(x, y)

        # Dragging variables
        self.drag_position = QPoint()

        # Audio state & reactive smoothing
        self.audio_level = 0.0
        self.voice_level = 0.0   # 0.0 = completely silent/transparent, 1.0 = loud/bright red
        self.fft_bands = np.zeros(NUM_BARS_PER_SIDE)
        self.left_bars = np.full(NUM_BARS_PER_SIDE, 4.0)
        self.right_bars = np.full(NUM_BARS_PER_SIDE, 4.0)
        self.anim_phase = 0.0

        # Start microphone input stream
        self.start_audio_stream()

        # 60 FPS animation render loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)

    def start_audio_stream(self):
        try:
            self.stream = sd.InputStream(
                channels=1,
                samplerate=SAMPLE_RATE,
                blocksize=CHUNK_SIZE,
                callback=self.audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"[ORION] Mic input fallback active (no audio stream): {e}")

    def audio_callback(self, indata, frames, time, status):
        if status:
            return
        audio_data = indata[:, 0]
        rms = float(np.sqrt(np.mean(audio_data**2)))

        if rms > NOISE_GATE:
            # Scaled so normal conversational speech quickly pushes to near 1.0
            normalized_vol = (rms - NOISE_GATE) / 0.035
            self.audio_level = min(1.0, max(0.0, normalized_vol))

            # FFT frequency distribution for speech bands
            fft_data = np.abs(np.fft.rfft(audio_data * np.hanning(len(audio_data))))
            freq_bins = np.array_split(fft_data[2:80], NUM_BARS_PER_SIDE)
            raw_bands = np.array([float(np.mean(b)) if len(b) > 0 else 0.0 for b in freq_bins])
            max_val = np.max(raw_bands) if np.max(raw_bands) > 0 else 1.0
            self.fft_bands = np.clip((raw_bands / max_val) * self.audio_level, 0.0, 1.0)
        else:
            self.audio_level = 0.0
            self.fft_bands = np.zeros(NUM_BARS_PER_SIDE)

    def update_animation(self):
        self.anim_phase += 0.08

        # Asymmetric smoothing: Instant attack when speaking, smooth release when silent
        if self.audio_level > self.voice_level:
            self.voice_level += (self.audio_level - self.voice_level) * 0.45
        else:
            self.voice_level += (self.audio_level - self.voice_level) * 0.10

        max_bar_h = 42.0

        for i in range(NUM_BARS_PER_SIDE):
            # Idle breathing pulse (faint when silent)
            idle_h = 3.5 + 2.0 * math.sin(self.anim_phase + i * 0.45)

            # Target height driven by audio volume + frequency band
            target_h = idle_h + (self.fft_bands[i] * max_bar_h)

            # Attack / Decay easing for equalizer bars
            self.left_bars[i] += (target_h - self.left_bars[i]) * 0.35
            right_target = idle_h + (self.fft_bands[NUM_BARS_PER_SIDE - 1 - i] * max_bar_h)
            self.right_bars[i] += (right_target - self.right_bars[i]) * 0.35

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        margin = 6.0
        capsule_rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)
        radius = capsule_rect.height() / 2.0

        v = max(0.0, min(1.0, self.voice_level))

        # --- Dynamic Alpha Ramps ---
        # Silent: very translucent red/dark tint (~35-45 alpha)
        # Voice: intense, saturated bright neon red (255 alpha)
        bg_alpha = int(50 + 185 * v)            # 50 -> 235
        border_alpha = int(35 + 220 * v)        # 35 -> 255
        glow_alpha = int(8 + 140 * v)           # 8  -> 148
        bars_alpha = int(30 + 225 * v)          # 30 -> 255
        subtext_alpha = int(40 + 215 * v)       # 40 -> 255
        text_alpha = int(90 + 165 * v)          # 90 -> 255
        divider_alpha = int(30 + 180 * v)       # 30 -> 210

        # 1. Background Fill (Translucent dark red when silent -> solid cyber-glass on voice)
        bg_red = int(10 + 15 * v)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(bg_red, 10, 16, bg_alpha)))
        painter.drawRoundedRect(capsule_rect, radius, radius)

        # 2. Outer Bloom & Neon Glow
        # Wide ambient glow pass
        painter.setPen(QPen(QColor(255, 20, 50, glow_alpha), 6.0 + 3.0 * v))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(capsule_rect, radius, radius)

        # Extra radiant bloom when actively speaking
        if v > 0.08:
            bloom_alpha = int(70 * v)
            painter.setPen(QPen(QColor(255, 0, 40, bloom_alpha), 11.0))
            painter.drawRoundedRect(capsule_rect, radius, radius)

        # Crisp primary neon border (Very transparent red -> Blazing solid red)
        border_thickness = 1.8 + 1.0 * v
        painter.setPen(QPen(QColor(255, 20, 50, border_alpha), border_thickness))
        painter.drawRoundedRect(capsule_rect, radius, radius)

        # 3. Equalizer Waveform Bars (Flanking Left & Right)
        center_y = h / 2.0
        bar_w = 2.8 + 0.6 * v
        bar_gap = 2.5
        bar_pen = QPen(QColor(255, 30, 60, bars_alpha), bar_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bar_pen)

        # Left visualizer bank
        start_x_left = 46.0
        for i in range(NUM_BARS_PER_SIDE):
            x = start_x_left + i * (bar_w + bar_gap)
            bar_height = max(3.0, self.left_bars[i] * (0.35 + 0.65 * v))
            y1 = center_y - (bar_height / 2.0)
            y2 = center_y + (bar_height / 2.0)
            painter.drawLine(QPoint(int(x), int(y1)), QPoint(int(x), int(y2)))

        # Right visualizer bank
        start_x_right = w - 46.0 - (NUM_BARS_PER_SIDE * (bar_w + bar_gap))
        for i in range(NUM_BARS_PER_SIDE):
            x = start_x_right + i * (bar_w + bar_gap)
            bar_height = max(3.0, self.right_bars[i] * (0.35 + 0.65 * v))
            y1 = center_y - (bar_height / 2.0)
            y2 = center_y + (bar_height / 2.0)
            painter.drawLine(QPoint(int(x), int(y1)), QPoint(int(x), int(y2)))

        # 4. Vertical Flanking Dividers
        divider_pen = QPen(QColor(240, 240, 245, divider_alpha), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(divider_pen)
        painter.drawLine(QPoint(135, int(center_y - 14)), QPoint(135, int(center_y + 14)))
        painter.drawLine(QPoint(int(w - 135), int(center_y - 14)), QPoint(int(w - 135), int(center_y + 14)))

        # 5. Centered Typography: "ORION" & "[ CODE RED ]"
        font_family = "Orbitron"
        if font_family not in QFontDatabase.families():
            font_family = "Segoe UI"

        # "ORION" (Dimmed when silent -> pure bright white when speaking)
        painter.setFont(QFont(font_family, 15, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255, text_alpha))
        title_rect = QRectF(135, center_y - 21, w - 270, 24)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "ORION")

        # "[ CODE RED ]" (Very faint red when silent -> laser bright red when speaking)
        painter.setFont(QFont(font_family, 7, QFont.Weight.Bold))
        painter.setPen(QColor(255, 30, 60, subtext_alpha))
        sub_rect = QRectF(135, center_y + 5, w - 270, 16)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "[ CODE RED ]")

    # --- Mouse Drag & Close Handlers ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bubble = OrionVoiceBubble()
    bubble.show()
    sys.exit(app.exec())