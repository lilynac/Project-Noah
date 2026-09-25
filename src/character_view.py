"""Lightweight portrait animation; this is not a rigged Live2D renderer."""
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QWidget, QSizePolicy


class CharacterView(QWidget):
    CAPTIONS = {
        'idle': '同じ時間を、あなたと。',
        'thinking': '言葉を選んでいます…',
        'reply': 'あなたへ、言葉を。',
        'boot': 'ゆっくり、目を覚ます。',
        'error': '少し待って、もう一度。',
    }

    def __init__(self, portrait_path=None, parent=None):
        super().__init__(parent)
        self.setAccessibleName('Noah のキャラクター')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.portrait = QPixmap(str(portrait_path)) if portrait_path else QPixmap()
        self.state = 'idle'
        self.motion_enabled = True
        self._started = time.monotonic()
        self._reply_until = 0.0
        self._pointer = QPointF()
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.reply_timer = QTimer(self)
        self.reply_timer.setSingleShot(True)
        self.reply_timer.timeout.connect(self._settle_reply)

    def set_state(self, state):
        self.state = state if state in self.CAPTIONS else 'idle'
        self._reply_until = time.monotonic() + 3.0 if state == 'reply' else 0.0
        self.reply_timer.stop()
        if state == 'reply':
            self.reply_timer.start(3000)
        self.update()

    def _settle_reply(self):
        if self.state == 'reply':
            self.state = 'idle'
            self.update()

    def set_motion_enabled(self, enabled):
        self.motion_enabled = bool(enabled)
        self._sync_timer()
        self.update()

    def _sync_timer(self):
        if self.motion_enabled and self.isVisible() and not self.window().isMinimized():
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _tick(self):
        if self.window().isMinimized():
            self.timer.stop()
            return
        if self.state == 'reply' and time.monotonic() >= self._reply_until:
            self.state = 'idle'
        self.update()

    def mouseMoveEvent(self, event):
        self._pointer = QPointF(event.position().x() / max(1, self.width()) - .5,
                                event.position().y() / max(1, self.height()) - .5)

    def leaveEvent(self, event):
        self._pointer = QPointF()
        super().leaveEvent(event)

    def source_rect(self):
        """Cover the panel with a face-biased crop when the window is narrow."""
        if self.portrait.isNull():
            return QRectF()
        width, height = self.portrait.width(), self.portrait.height()
        ratio = self.width() / max(1, self.height())
        if width / height > ratio:
            crop_width = height * ratio
            return QRectF((width - crop_width) / 2, 0, crop_width, height)
        crop_height = width / ratio
        top = max(0, min(height - crop_height, height * .31 - crop_height / 2))
        return QRectF(0, top, width, crop_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 24, 24)
        painter.setClipPath(clip)
        painter.fillRect(bounds, QColor('#263d35'))
        elapsed = time.monotonic() - self._started
        if not self.portrait.isNull():
            painter.save()
            painter.translate(bounds.center())
            # A single image can breathe and gently tilt; eyes/mouth are unchanged.
            if self.motion_enabled:
                breath = math.sin(elapsed * 1.25)
                nod = 0.0
                if self.state == 'reply':
                    remaining = max(0, self._reply_until - time.monotonic())
                    nod = math.sin(remaining * 3) * remaining / 3 * .7
                painter.rotate(math.sin(elapsed * .55) * .25 + nod)
                painter.translate(self._pointer.x() * 3, breath * 1.5 + self._pointer.y() * 2)
                painter.scale(1.025, 1.025 + breath * .004)
            painter.translate(-bounds.center())
            painter.drawPixmap(bounds, self.portrait, self.source_rect())
            painter.restore()
        gradient = QLinearGradient(0, self.height() * .55, 0, self.height())
        gradient.setColorAt(0, QColor(15, 27, 23, 0))
        gradient.setColorAt(1, QColor(15, 27, 23, 220))
        painter.fillRect(bounds, gradient)
        painter.setPen(QColor('#ffffff'))
        font = QFont(self.font())
        font.setPixelSize(30 if self.height() > 300 else 24)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(24, self.height() - 88, self.width() - 48, 42), 'Noah')
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor('#ecece2'))
        caption = self.CAPTIONS[self.state]
        if self.portrait.isNull():
            caption = 'あなたの声を、聞いているよ。'
        painter.drawText(QRectF(24, self.height() - 43, self.width() - 48, 24), caption)
        painter.end()
