from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget


class BubbleTipWidget(QWidget):
    """滑杆上方气泡数值提示：圆角矩形 + 底部居中三角指针。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._bg_color = QColor(0x78, 0x9E, 0xFF)
        self._text_color = QColor(255, 255, 255)
        self._radius = 8.0
        self._tail_height = 7.0
        self._tail_half_width = 5.0
        self._pad_h = 12
        self._pad_v = 5

        font = self.font()
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.Normal)
        self.setFont(font)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def setText(self, text: str) -> None:
        text = str(text or "")
        if text == self._text:
            return
        self._text = text
        self._apply_text_size()
        self.update()

    def text(self) -> str:
        return self._text

    def _apply_text_size(self) -> None:
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()
        width = max(36, text_w + 2 * self._pad_h)
        body_h = text_h + 2 * self._pad_v
        height = int(body_h + self._tail_height)
        self.setFixedSize(width, height)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        body_h = h - self._tail_height
        body = QRectF(0.0, 0.0, w, body_h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(body, self._radius, self._radius)

        cx = w / 2.0
        tail = QPolygonF(
            [
                QPointF(cx - self._tail_half_width, body_h - 1.0),
                QPointF(cx, h),
                QPointF(cx + self._tail_half_width, body_h - 1.0),
            ]
        )
        painter.drawPolygon(tail)

        painter.setPen(self._text_color)
        painter.drawText(body, int(Qt.AlignCenter), self._text)
