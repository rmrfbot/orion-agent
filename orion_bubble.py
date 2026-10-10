import json
import sys
import math
import queue
import re
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QApplication, QWidget
from vosk import KaldiRecognizer, Model


WAKE_WORDS = {"orion", "ryan", "oreon", "orian", "rion"}
WAKE_PREFIXES = {"hey", "they"}


def wake_phrase_length(words):
    if len(words) > 1 and words[0] in WAKE_PREFIXES and words[1] in WAKE_WORDS:
        return 2
    if words and words[0] in WAKE_WORDS:
        return 1
    return 0


class OrionDesktopBubble(QWidget):
    voice_status_changed = pyqtSignal(str)

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
        self.voice_status = "Starting local voice listener..."
        self.audio_queue = queue.Queue(maxsize=32)
        self.stop_listener = threading.Event()
        self.awaiting_command_until = 0
        self.voice_status_changed.connect(self._set_voice_status)

        # Start live microphone audio stream
        try:
            self.stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=4000,
                dtype="float32",
                callback=self._audio_callback
            )
            self.stream.start()
            self.has_mic = True
        except Exception as e:
            self.voice_status = f"Microphone unavailable: {e}"
            print(f"[Orion] {self.voice_status}")
            self.has_mic = False

        model_path = Path(__file__).resolve().parent / "models" / "vosk-model-small-en-us-0.15"
        self.recognizer = None
        if self.has_mic and model_path.is_dir():
            try:
                self.recognizer = KaldiRecognizer(Model(str(model_path)), 16000)
                self.listener_thread = threading.Thread(
                    target=self._listen_for_commands,
                    daemon=True,
                )
                self.listener_thread.start()
                self.voice_status = "Listening locally: say 'Hey Orion'"
                print("[Orion] Local speech listener ready. Say 'Hey Orion' or 'Orion'.")
            except Exception as e:
                self.voice_status = f"Could not load local speech model: {e}"
                print(f"[Orion] {self.voice_status}")
        elif not model_path.is_dir():
            self.voice_status = "Install the Vosk model; see README"

        # 60 FPS Render Loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def _audio_callback(self, indata, frames, time, status):
        if indata.size > 0:
            # FFT frequency analysis for reactive bars
            samples = indata[:, 0].copy()
            fft_vals = np.abs(np.fft.rfft(samples))[:self.num_bars]
            norm_vals = np.clip(fft_vals / max(len(samples), 1) / 0.08, 0, 1)
            # Smooth transition
            self.audio_levels = self.audio_levels * 0.4 + norm_vals * 0.6
            try:
                self.audio_queue.put_nowait(samples)
            except queue.Full:
                pass

    def _listen_for_commands(self):
        last_partial = ""
        while not self.stop_listener.is_set():
            try:
                samples = self.audio_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            pcm = np.clip(samples * 32767, -32768, 32767).astype(np.int16).tobytes()
            if self.recognizer.AcceptWaveform(pcm):
                transcript = json.loads(self.recognizer.Result()).get("text", "")
                last_partial = ""
                self._handle_transcript(transcript)
            else:
                partial = json.loads(self.recognizer.PartialResult()).get("partial", "")
                if partial and partial != last_partial:
                    last_partial = partial
                    self.voice_status_changed.emit(f"Hearing: {partial[:36]}")

    def _handle_transcript(self, transcript):
        words = re.sub(r"[^a-z0-9 ]", " ", transcript.lower()).split()
        if not words:
            return

        wake_length = wake_phrase_length(words)

        if wake_length:
            command = " ".join(words[wake_length:]).strip()
            if command:
                self.awaiting_command_until = 0
                self.voice_status_changed.emit(f"Sending: {command[:34]}")
                threading.Thread(
                    target=self._send_command,
                    args=(command,),
                    daemon=True,
                ).start()
            else:
                self.awaiting_command_until = time.monotonic() + 10
                self.voice_status_changed.emit("Listening for your command...")
            return

        if time.monotonic() <= self.awaiting_command_until:
            self.awaiting_command_until = 0
            command = " ".join(words)
            self.voice_status_changed.emit(f"Sending: {command[:34]}")
            threading.Thread(
                target=self._send_command,
                args=(command,),
                daemon=True,
            ).start()
        else:
            self.voice_status_changed.emit(
                f"Heard '{' '.join(words)[:24]}'; say Orion first"
            )

    def _send_command(self, command):
        request = urllib.request.Request(
            "http://127.0.0.1:8000/voice/command",
            data=json.dumps({"command": command}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("queued"):
                self.voice_status_changed.emit("Command sent to browser")
            else:
                self.voice_status_changed.emit("Backend did not queue command")
        except Exception as e:
            self.voice_status_changed.emit(f"Backend unavailable: {e}")

    def _set_voice_status(self, message):
        self.voice_status = message
        self.update()

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

        status_font = QFont("Segoe UI", 8)
        painter.setFont(status_font)
        painter.setPen(QPen(QColor(220, 230, 235)))
        painter.drawText(
            center_x - 150,
            center_y + 52,
            300,
            36,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.voice_status,
        )

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
        self.stop_listener.set()
        if hasattr(self, "stream"):
            self.stream.stop()
            self.stream.close()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bubble = OrionDesktopBubble()
    bubble.show()
    print("[Orion] Bubble launched! Click and drag to move it. Press ESC to close.")
    sys.exit(app.exec())