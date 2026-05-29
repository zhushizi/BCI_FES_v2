"""
圆环等级滑块控件：可显示/可拖动圆环，中心显示当前等级（如 5 级）。
支持只读模式：仅显示、与 label 联动，不可拖动。
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPen, QBrush, QRadialGradient, QMouseEvent
from PySide6.QtWidgets import QWidget


class CircleLevelWidget(QWidget):
    """圆形电流强度控件：浅色仪表环、蓝色进度弧、末端闪电手柄，中心显示 mA。"""

    levelChanged = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min_level = 0
        self._max_level = 99
        self._level = 0
        self._dragging = False
        self._read_only = False

        self._track_color = QColor(240, 244, 251)
        self._tick_color = QColor(219, 224, 232)
        self._label_color = QColor(164, 171, 184)
        self._arc_color = QColor(127, 160, 255)
        self._handle_color = QColor(122, 156, 246)
        self._handle_highlight = QColor(255, 255, 255)
        self._bg_color = QColor(255, 255, 255)
        self._text_color = QColor(74, 122, 226)

        self.setMinimumSize(120, 120)
        self.setMouseTracking(False)

    def level(self) -> int:
        return self._level

    def set_level(self, value: int) -> None:
        v = max(self._min_level, min(self._max_level, int(value)))
        if v != self._level:
            self._level = v
            self.update()
            self.levelChanged.emit(self._level)

    def set_level_range(self, min_level: int, max_level: int) -> None:
        self._min_level = max(0, int(min_level))
        self._max_level = max(self._min_level, int(max_level))
        self._level = max(self._min_level, min(self._max_level, self._level))
        self.update()

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = bool(read_only)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, read_only)

    def is_read_only(self) -> bool:
        return self._read_only

    def _angle_for_level(self, level: int) -> float:
        if self._max_level <= self._min_level:
            return self._gauge_start_angle()
        t = (level - self._min_level) / (self._max_level - self._min_level)
        return self._gauge_start_angle() + t * self._gauge_sweep_angle()

    def _level_from_angle(self, angle_deg: float) -> int:
        if self._max_level <= self._min_level:
            return self._min_level
        delta = (angle_deg - self._gauge_start_angle()) % 360.0
        sweep = self._gauge_sweep_angle()
        if delta > sweep:
            dist_to_start = min(delta, 360.0 - delta)
            dist_to_end = min(abs(delta - sweep), 360.0 - abs(delta - sweep))
            delta = 0.0 if dist_to_start <= dist_to_end else sweep
        t = max(0.0, min(1.0, delta / sweep))
        return self._min_level + int(round(t * (self._max_level - self._min_level)))

    def _center_rect(self) -> QRectF:
        r = self.rect()
        side = min(r.width(), r.height())
        cx = r.x() + r.width() / 2
        cy = r.y() + r.height() / 2
        return QRectF(cx - side / 2, cy - side / 2, side, side)

    def _handle_radius_px(self) -> float:
        return 14.0

    def _track_width(self) -> float:
        return min(self.width(), self.height()) * 0.105

    def _track_outer_diameter(self) -> float:
        """灰色圆环外径（px），随宿主尺寸缩放。"""
        return min(self.width(), self.height()) * 0.80

    def _gauge_start_angle(self) -> float:
        """0mA 位于左下方，顺时针扫过 270 度到右下方。"""
        return 225.0

    def _gauge_sweep_angle(self) -> float:
        return 270.0

    def _angle_for_scale_value(self, value: int) -> float:
        if self._max_level <= self._min_level:
            return self._gauge_start_angle()
        t = (value - self._min_level) / (self._max_level - self._min_level)
        return self._gauge_start_angle() + t * self._gauge_sweep_angle()

    def _angle_to_point(self, cx: float, cy: float, radius: float, angle_deg: float) -> QPointF:
        rad = math.radians(-angle_deg + 90)
        return QPointF(cx + radius * math.cos(rad), cy - radius * math.sin(rad))

    def _point_to_angle(self, cx: float, cy: float, x: float, y: float) -> float:
        dx = x - cx
        dy = cy - y
        a = math.degrees(math.atan2(dx, dy))
        if a < 0:
            a += 360.0
        return a

    def _hit_handle(self, cx: float, cy: float, radius: float, x: float, y: float) -> bool:
        p = self._angle_to_point(cx, cy, radius, self._angle_for_level(self._level))
        d = math.hypot(x - p.x(), y - p.y())
        return d <= self._handle_radius_px() + 4

    def _draw_ticks(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.save()
        tick_color = QColor(self._tick_color)
        tick_color.setAlpha(155)
        pen = QPen(tick_color, 1.0, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        label_angles = [self._angle_for_scale_value(value) for value in (0, 20, 40, 60, 80)]
        for step in range(0, 49):
            angle = self._gauge_start_angle() + self._gauge_sweep_angle() * step / 48
            if any(abs((angle - label_angle + 180.0) % 360.0 - 180.0) < 7.0 for label_angle in label_angles):
                continue
            outer = self._angle_to_point(cx, cy, radius, float(angle))
            inner = self._angle_to_point(cx, cy, radius - 6.0, float(angle))
            painter.drawLine(inner, outer)
        painter.restore()

    def _draw_scale_labels(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.save()
        font = QFont(self.font())
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(self._label_color)
        label_w = 42.0
        label_h = 14.0
        margin = 5.0
        for value in (0, 20, 40, 60, 80):
            angle = self._angle_for_scale_value(value)
            p = self._angle_to_point(cx, cy, radius, angle)
            x = max(margin, min(self.width() - label_w - margin, p.x() - label_w / 2))
            y = max(margin, min(self.height() - label_h - margin, p.y() - label_h / 2))
            label_rect = QRectF(x, y, label_w, label_h)
            painter.drawText(label_rect, Qt.AlignCenter, f"{value}mA")
        painter.restore()

    def _arc_gradient(self, cx: float, cy: float) -> QConicalGradient:
        gradient = QConicalGradient(QPointF(cx, cy), 90.0 - self._gauge_start_angle())
        gradient.setColorAt(0.00, QColor(158, 187, 255))
        gradient.setColorAt(0.35, QColor(126, 164, 255))
        gradient.setColorAt(0.75, QColor(91, 128, 246))
        gradient.setColorAt(1.00, QColor(158, 187, 255))
        return gradient

    def _handle_gradient(self, center: QPointF, radius: float) -> QRadialGradient:
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.00, QColor(151, 181, 255))
        gradient.setColorAt(0.70, QColor(118, 154, 246))
        gradient.setColorAt(1.00, QColor(96, 135, 242))
        return gradient

    def _draw_center_disc(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.save()
        for i, alpha in enumerate((28, 18, 10, 5)):
            grow = i * 3.0
            offset_y = 3.0 + i * 1.4
            shadow_rect = QRectF(
                cx - radius - grow,
                cy - radius + offset_y - grow,
                (radius + grow) * 2,
                (radius + grow) * 2,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(100, 120, 150, alpha))
            painter.drawEllipse(shadow_rect)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(226, 232, 240), 1.0))
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        painter.restore()

    def _draw_lightning(self, painter: QPainter, center: QPointF, size: float) -> None:
        painter.save()
        path = QPainterPath()
        path.moveTo(center.x() + size * 0.05, center.y() - size * 0.48)
        path.lineTo(center.x() - size * 0.28, center.y() + size * 0.03)
        path.lineTo(center.x() - size * 0.03, center.y() + size * 0.03)
        path.lineTo(center.x() - size * 0.12, center.y() + size * 0.48)
        path.lineTo(center.x() + size * 0.30, center.y() - size * 0.12)
        path.lineTo(center.x() + size * 0.04, center.y() - size * 0.12)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._handle_highlight))
        painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        outer_r = self._track_outer_diameter() / 2
        radius_mid = outer_r - self._track_width() / 2
        center_r = min(rect.width(), rect.height()) * 0.245

        painter.fillRect(self.rect(), self._bg_color)
        self._draw_ticks(painter, cx, cy, min(rect.width(), rect.height()) * 0.487)

        track_rect = QRectF(
            cx - radius_mid,
            cy - radius_mid,
            radius_mid * 2,
            radius_mid * 2,
        )
        pen_track = QPen(self._track_color, self._track_width(), Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(track_rect)

        angle_deg = self._angle_for_level(self._level) % 360.0
        progress_sweep = (angle_deg - self._gauge_start_angle()) % 360.0
        progress_sweep = min(progress_sweep, self._gauge_sweep_angle())
        pen_arc = QPen(QBrush(self._arc_gradient(cx, cy)), self._track_width(), Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(
            track_rect,
            int((90.0 - self._gauge_start_angle()) * 16),
            -int(progress_sweep * 16),
        )

        self._draw_center_disc(painter, cx, cy, center_r)

        handle_pos = self._angle_to_point(cx, cy, radius_mid, angle_deg)
        hr = self._handle_radius_px()
        handle_rect = QRectF(handle_pos.x() - hr, handle_pos.y() - hr, hr * 2, hr * 2)
        painter.setPen(QPen(self._handle_highlight, 1.6))
        painter.setBrush(QBrush(self._handle_gradient(handle_pos, hr)))
        painter.drawEllipse(handle_rect)
        self._draw_lightning(painter, handle_pos, hr * 0.82)

        self._draw_scale_labels(painter, cx, cy, min(rect.width(), rect.height()) * 0.465)

        text = f"{self._level}mA"
        font = QFont(self.font())
        font.setPointSize(max(18, min(30, int(self._track_outer_diameter() / 9.2))))
        painter.setFont(font)
        painter.setPen(self._text_color)
        painter.drawText(
            QRectF(cx - center_r, cy - center_r, center_r * 2, center_r * 2),
            Qt.AlignCenter,
            text,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._read_only:
            return
        if event.button() != Qt.LeftButton:
            return
        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        outer_r = self._track_outer_diameter() / 2
        radius_mid = outer_r - self._track_width() / 2

        if self._hit_handle(cx, cy, radius_mid, event.position().x(), event.position().y()):
            self._dragging = True
            return
        dx = event.position().x() - cx
        dy = event.position().y() - cy
        d = math.hypot(dx, dy)
        if abs(d - radius_mid) <= self._track_width() + 8:
            self.set_level(self._level_from_angle(self._point_to_angle(cx, cy, event.position().x(), event.position().y())))
            self._dragging = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._read_only:
            return
        if not self._dragging:
            return
        rect = self._center_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        angle = self._point_to_angle(cx, cy, event.position().x(), event.position().y())
        self.set_level(self._level_from_angle(angle))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
