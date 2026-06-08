from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QEvent, Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QBrush, QPixmap
from PySide6.QtWidgets import QWidget


class SliderWidget(QWidget):
    """
    通用滑杆控件：

    - 竖直模式（默认）：顶部=最小值，底部=最大值
    - 横向模式（当控件宽明显大于高时自动启用）：左侧=最小值，右侧=最大值

    - 竖直方向带倒角的轨道
    - 蓝色渐变自轨道顶部填至手柄
    - 圆形手柄与轨道左右相切
    - 可复用于脉冲宽度、阈值等数值选择
    """

    valueChanged = Signal(int)
    sliderReleased = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min_value = 0
        self._max_value = 100
        self._value = 50
        self._dragging = False

        # 透明背景：让父级 widget 的背景透出
        self._bg_color = QColor(0, 0, 0, 0)
        self._track_border_color = QColor(224, 228, 235)
        self._track_fill_top = QColor(153, 178, 255)
        self._track_fill_bottom = QColor(88, 122, 244)
        self._handle_color = QColor(88, 122, 244)
        self._handle_inner_color = QColor(255, 255, 255)
        self._track_base_color = QColor(255, 255, 255)
        # vertical_style: "gradient" 默认；"pill" 为脉冲宽度参考图样式
        self._vertical_style = "gradient"
        self._tick_count = 0
        self._pill_track_width = 24.0
        self._pill_handle_track_ratio = 1.6
        self._pill_track_idle = QColor(233, 237, 245)
        self._pill_track_active = QColor(0x78, 0x9E, 0xFF)  # #789EFF
        self._pill_track_border = QColor(208, 214, 224)
        self._pill_handle_fill = QColor(255, 255, 255)
        self._pill_handle_border = QColor(216, 222, 232)
        self._pill_handle_icon = QColor(118, 154, 246)
        self._pill_handle_icon_pixmap: Optional[QPixmap] = None
        self._pill_handle_icon_ratio = 0.46
        self._pill_tick_idle = QColor(196, 202, 214)
        self._pill_tick_active = QColor(255, 255, 255)
        self._apply_active_palette()

        # 默认允许薄横向条；竖向宿主在首次 resize 后会提高到 120
        self.setMinimumSize(40, 16)
        self.setMouseTracking(False)
        # 允许使用透明背景
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    # ----------- 对外接口 -----------
    def set_range(self, minimum: int, maximum: int) -> None:
        if maximum <= minimum:
            maximum = minimum + 1
        self._min_value = int(minimum)
        self._max_value = int(maximum)
        self.set_value(self._value)

    def set_value(self, value: int) -> None:
        v = max(self._min_value, min(self._max_value, int(value)))
        if v == self._value:
            return
        self._value = v
        self.update()
        self.valueChanged.emit(self._value)

    def value(self) -> int:
        return self._value

    def set_vertical_style(self, style: str) -> None:
        """滑杆样式：gradient（默认）或 pill（圆角轨道 + 刻度点 + 白色手柄，横/竖向均可用）。"""
        style = str(style or "gradient").lower()
        if style not in ("gradient", "pill"):
            style = "gradient"
        if style != self._vertical_style:
            self._vertical_style = style
            self.update()

    def set_tick_count(self, count: int) -> None:
        """竖直 pill 样式下沿轨道绘制的刻度点数量；0 表示不绘制。"""
        count = max(0, int(count))
        if count != self._tick_count:
            self._tick_count = count
            self.update()

    def set_pill_handle_icon(self, resource_path: str) -> None:
        """pill 摇杆中心图标（资源路径，如 :/set/pic/icon_yaogan_time.png）；未设置则绘制闪电。"""
        path = str(resource_path or "").strip()
        pixmap = QPixmap(path) if path else QPixmap()
        self._pill_handle_icon_pixmap = None if pixmap.isNull() else pixmap
        self.update()

    def _apply_active_palette(self) -> None:
        self._track_border_color = QColor(224, 228, 235)
        self._track_base_color = QColor(255, 255, 255)
        self._track_fill_top = QColor(153, 178, 255)
        self._track_fill_bottom = QColor(88, 122, 244)
        self._handle_color = QColor(88, 122, 244)
        self._handle_inner_color = QColor(255, 255, 255)

    def _apply_disabled_palette(self) -> None:
        self._track_border_color = QColor(220, 224, 230)
        self._track_base_color = QColor(236, 238, 242)
        self._track_fill_top = QColor(210, 216, 228)
        self._track_fill_bottom = QColor(200, 206, 218)
        self._handle_color = QColor(200, 206, 218)
        self._handle_inner_color = QColor(245, 246, 248)

    def _sync_visual_palette(self) -> None:
        if self.isEnabled():
            self._apply_active_palette()
        else:
            self._apply_disabled_palette()
        self.update()

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        self._sync_visual_palette()

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._sync_visual_palette()

    def _is_horizontal(self) -> bool:
        # UI 里把容器拉成“横条状”时自动切换绘制/交互方向
        return self.width() >= self.height() * 1.3

    def _apply_minimum_size(self) -> None:
        """横向薄条容器（如 806×33）需允许较小高度，否则轨道会被裁到可视区外。"""
        if self.width() > 0 and self.height() > 0 and self._is_horizontal():
            self.setMinimumSize(80, 16)
        else:
            self.setMinimumSize(40, 120)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_minimum_size()

    # ----------- 内部几何计算 -----------
    def _track_geometry(self) -> Tuple[QRectF, float, float]:
        """
        返回 (轨道矩形, 圆角半径/手柄半径, 有效移动长度)。
        有效移动长度 = 轨道长度 - 2 * 半径。
        """
        rect = self.rect()
        if self._is_horizontal():
            margin_x = rect.width() * (0.04 if self._vertical_style == "pill" else 0.06)
            if self._vertical_style == "pill":
                track_h = self._pill_track_width
                pad_y = max(2.0, (rect.height() - track_h) / 2.0)
            else:
                pad_y = min(6.0, max(2.0, rect.height() * 0.1))
                track_h = max(12.0, rect.height() - 2.0 * pad_y)
            track_rect = QRectF(
                rect.left() + margin_x,
                rect.center().y() - track_h / 2.0,
                max(40.0, rect.width() - 2 * margin_x),
                track_h,
            )
            radius = track_rect.height() / 2.0
            effective_len = max(1.0, track_rect.width() - 2.0 * radius)
            return track_rect, radius, effective_len

        margin_y = rect.height() * 0.08
        if self._vertical_style == "pill":
            # 按宿主宽度比例取轨道宽（约 120px 宿主 → 34px 轨道）
            track_width = max(self._pill_track_width, min(36.0, rect.width() * 0.28))
            track_rect = QRectF(
                rect.center().x() - track_width / 2.0,
                rect.top() + margin_y,
                track_width,
                max(20.0, rect.height() - 2 * margin_y),
            )
        else:
            margin_x = rect.width() * 0.3
            track_width = max(10.0, rect.width() - 2 * margin_x)
            track_rect = QRectF(
                rect.center().x() - track_width / 2.0,
                rect.top() + margin_y,
                track_width,
                max(20.0, rect.height() - 2 * margin_y),
            )
        radius = track_rect.width() / 2.0
        effective_len = max(1.0, track_rect.height() - 2.0 * radius)
        return track_rect, radius, effective_len

    def _handle_radius(self) -> float:
        if self._vertical_style == "pill":
            track_rect, _, _ = self._track_geometry()
            track_cross = track_rect.height() if self._is_horizontal() else track_rect.width()
            return track_cross * self._pill_handle_track_ratio / 2.0
        _, radius, _ = self._track_geometry()
        return radius

    def _value_ratio(self) -> float:
        if self._max_value <= self._min_value:
            return 0.0
        return (self._value - self._min_value) / float(self._max_value - self._min_value)

    def _handle_center(self) -> QPointF:
        """手柄位置：竖直(上小下大) / 横向(左小右大)。"""
        track_rect, radius, effective_len = self._track_geometry()
        t = self._value_ratio()
        if self._is_horizontal():
            left_center_x = track_rect.left() + radius
            center_x = left_center_x + t * effective_len
            center_y = track_rect.center().y()
            return QPointF(center_x, center_y)
        center_x = track_rect.center().x()
        top_center_y = track_rect.top() + radius
        center_y = top_center_y + t * effective_len
        return QPointF(center_x, center_y)

    def _value_from_pos(self, pos: QPointF) -> int:
        """从坐标反算数值：竖直用 y，横向用 x。"""
        track_rect, radius, effective_len = self._track_geometry()
        if self._is_horizontal():
            left_center_x = track_rect.left() + radius
            t = (pos.x() - left_center_x) / effective_len
        else:
            top_center_y = track_rect.top() + radius
            t = (pos.y() - top_center_y) / effective_len
        t = max(0.0, min(1.0, t))
        value = self._min_value + t * (self._max_value - self._min_value)
        return int(round(value))

    def _draw_pill_track(self, painter: QPainter, track_rect: QRectF, radius: float) -> QPainterPath:
        path_track = QPainterPath()
        path_track.addRoundedRect(track_rect, radius, radius)

        border_color = self._pill_track_border if self.isEnabled() else self._track_border_color
        fill_color = self._pill_track_idle if self.isEnabled() else self._track_base_color
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(fill_color)
        painter.drawPath(path_track)
        return path_track

    def _draw_handle_icon(self, painter: QPainter, center: QPointF, hr: float) -> None:
        pixmap = self._pill_handle_icon_pixmap
        if pixmap is None or pixmap.isNull():
            self._draw_lightning(painter, center, hr * 0.82)
            return
        icon_size = hr * 2.0 * self._pill_handle_icon_ratio
        scaled = pixmap.scaled(
            int(icon_size),
            int(icon_size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.save()
        if not self.isEnabled():
            painter.setOpacity(0.45)
        painter.drawPixmap(
            int(center.x() - scaled.width() / 2.0),
            int(center.y() - scaled.height() / 2.0),
            scaled,
        )
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
        icon_color = self._pill_handle_icon if self.isEnabled() else self._handle_color
        painter.setBrush(QBrush(icon_color))
        painter.drawPath(path)
        painter.restore()

    def _draw_pill_handle(self, painter: QPainter, handle_center: QPointF, hr: float) -> None:
        handle_rect = QRectF(
            handle_center.x() - hr,
            handle_center.y() - hr,
            hr * 2.0,
            hr * 2.0,
        )
        fill_color = self._pill_handle_fill if self.isEnabled() else self._handle_inner_color
        border_color = self._pill_handle_border if self.isEnabled() else self._track_border_color
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(QBrush(fill_color))
        painter.drawEllipse(handle_rect)
        self._draw_handle_icon(painter, handle_center, hr)

    def _paint_vertical_pill(self, painter: QPainter) -> None:
        track_rect, radius, _ = self._track_geometry()
        handle_center = self._handle_center()
        hr = self._handle_radius()

        path_track = self._draw_pill_track(painter, track_rect, radius)

        fill_top = track_rect.top()
        fill_h = max(0.0, handle_center.y() - fill_top)
        if fill_h > 0:
            fill_rect = QRectF(track_rect.left(), fill_top, track_rect.width(), fill_h)
            painter.save()
            painter.setClipPath(path_track)
            painter.fillRect(fill_rect, self._pill_track_active if self.isEnabled() else self._track_fill_bottom)
            painter.restore()

        tick_n = self._tick_count
        if tick_n >= 2 and self.isEnabled():
            travel_top = track_rect.top() + radius
            travel_bottom = track_rect.bottom() - radius
            dot_r = max(2.8, track_rect.width() * 0.16)
            cx = track_rect.center().x()
            for i in range(tick_n):
                t = i / float(tick_n - 1)
                y = travel_top + t * (travel_bottom - travel_top)
                on_active = y <= handle_center.y() + 0.5
                color = self._pill_tick_active if on_active else self._pill_tick_idle
                painter.setBrush(color)
                painter.drawEllipse(QPointF(cx, y), dot_r, dot_r)

        self._draw_pill_handle(painter, handle_center, hr)

    def _paint_horizontal_pill(self, painter: QPainter) -> None:
        track_rect, radius, _ = self._track_geometry()
        handle_center = self._handle_center()
        hr = self._handle_radius()

        path_track = self._draw_pill_track(painter, track_rect, radius)

        fill_left = track_rect.left()
        fill_w = max(0.0, handle_center.x() - fill_left)
        if fill_w > 0:
            fill_rect = QRectF(fill_left, track_rect.top(), fill_w, track_rect.height())
            painter.save()
            painter.setClipPath(path_track)
            painter.fillRect(fill_rect, self._pill_track_active if self.isEnabled() else self._track_fill_bottom)
            painter.restore()

        tick_n = self._tick_count
        if tick_n >= 2 and self.isEnabled():
            travel_left = track_rect.left() + radius
            travel_right = track_rect.right() - radius
            dot_r = max(2.8, track_rect.height() * 0.16)
            cy = track_rect.center().y()
            for i in range(tick_n):
                t = i / float(tick_n - 1)
                x = travel_left + t * (travel_right - travel_left)
                on_active = x <= handle_center.x() + 0.5
                color = self._pill_tick_active if on_active else self._pill_tick_idle
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, cy), dot_r, dot_r)

        self._draw_pill_handle(painter, handle_center, hr)

    def _paint_default(self, painter: QPainter) -> None:
        track_rect, radius, _ = self._track_geometry()

        path_track = QPainterPath()
        path_track.addRoundedRect(track_rect, radius, radius)
        painter.setPen(QPen(self._track_border_color, 1))
        painter.setBrush(QBrush(self._track_base_color))
        painter.drawPath(path_track)

        handle_center = self._handle_center()
        if self._is_horizontal():
            fill_left = track_rect.left()
            fill_right = max(handle_center.x(), track_rect.left())
            fill_rect = QRectF(fill_left, track_rect.top(), fill_right - fill_left, track_rect.height())
            should_fill = fill_rect.width() > 0
            gradient = QLinearGradient(
                fill_rect.left(),
                track_rect.center().y(),
                fill_rect.right(),
                track_rect.center().y(),
            )
        else:
            fill_top = track_rect.top()
            fill_bottom = max(handle_center.y(), track_rect.top())
            fill_rect = QRectF(track_rect.left(), fill_top, track_rect.width(), fill_bottom - fill_top)
            should_fill = fill_rect.height() > 0
            gradient = QLinearGradient(
                track_rect.center().x(),
                fill_rect.top(),
                track_rect.center().x(),
                fill_rect.bottom(),
            )

        if should_fill:
            gradient.setColorAt(0.0, self._track_fill_top)
            gradient.setColorAt(1.0, self._track_fill_bottom)
            painter.save()
            painter.setClipPath(path_track)
            painter.fillRect(fill_rect, gradient)
            painter.restore()

        hr = self._handle_radius()
        handle_rect = QRectF(
            handle_center.x() - hr,
            handle_center.y() - hr,
            hr * 2.0,
            hr * 2.0,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._handle_color))
        painter.drawEllipse(handle_rect)

        inner_r = hr * 0.85
        inner_rect = QRectF(
            handle_center.x() - inner_r,
            handle_center.y() - inner_r,
            inner_r * 2.0,
            inner_r * 2.0,
        )
        painter.setBrush(QBrush(self._handle_inner_color))
        painter.drawEllipse(inner_rect)

    # ----------- 绘制 -----------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), self._bg_color)

        if self._vertical_style == "pill":
            if self._is_horizontal():
                self._paint_horizontal_pill(painter)
            else:
                self._paint_vertical_pill(painter)
        else:
            self._paint_default(painter)

    # ----------- 交互 -----------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        handle_center = self._handle_center()
        track_rect, _, _ = self._track_geometry()
        hr = self._handle_radius()
        dx = event.position().x() - handle_center.x()
        dy = event.position().y() - handle_center.y()
        if dx * dx + dy * dy <= (hr + 4.0) * (hr + 4.0):
            self._dragging = True
            event.accept()
            return

        if track_rect.contains(event.position()):
            self.set_value(self._value_from_pos(event.position()))
            self._dragging = True
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        self.set_value(self._value_from_pos(event.position()))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
