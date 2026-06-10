"""表格行/表头复选框（#789EFF 选中样式，自绘勾选标记）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QEvent, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHeaderView, QWidget

_CHECKBOX_CHECKED_COLOR = "#789EFF"
_CHECKBOX_UNCHECKED_BORDER = "#D0D5DD"
_CHECKBOX_SIZE = 18


def coerce_check_state(state) -> Qt.CheckState:
    if isinstance(state, Qt.CheckState):
        return state
    return Qt.CheckState(int(state))


def check_state_value(state: Qt.CheckState) -> int:
    return coerce_check_state(state).value


def paint_checkbox_indicator(painter: QPainter, rect: QRect, state: Qt.CheckState) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked):
        painter.setBrush(QColor(_CHECKBOX_CHECKED_COLOR))
        painter.setPen(QColor(_CHECKBOX_CHECKED_COLOR))
    else:
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QColor(_CHECKBOX_UNCHECKED_BORDER))
    painter.drawRoundedRect(rect, 4, 4)

    if state == Qt.CheckState.Checked:
        pen = QPen(
            QColor("#FFFFFF"),
            2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        painter.drawLine(int(x + w * 0.22), int(y + h * 0.52), int(x + w * 0.42), int(y + h * 0.72))
        painter.drawLine(int(x + w * 0.42), int(y + h * 0.72), int(x + w * 0.78), int(y + h * 0.30))
    elif state == Qt.CheckState.PartiallyChecked:
        pen = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        painter.drawLine(int(x + w * 0.24), int(y + h * 0.5), int(x + w * 0.76), int(y + h * 0.5))
    painter.restore()


class TableCheckBox(QWidget):
    """自绘复选框，与表头样式一致。"""

    stateChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = Qt.CheckState.Unchecked
        self.setFixedSize(_CHECKBOX_SIZE, _CHECKBOX_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def checkState(self) -> Qt.CheckState:
        return self._state

    def setCheckState(self, state: Qt.CheckState) -> None:
        state = coerce_check_state(state)
        if state == self._state:
            return
        self._state = state
        self.update()
        self.stateChanged.emit(check_state_value(state))

    def setChecked(self, checked: bool) -> None:
        self.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        paint_checkbox_indicator(painter, self.rect(), self._state)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = (
                Qt.CheckState.Unchecked
                if self._state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            self.setCheckState(new_state)
        super().mousePressEvent(event)


class TableCheckBoxHeader(QHeaderView):
    """表头第 0 列全选复选框。"""

    checkStateChanged = Signal(Qt.CheckState)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._check_state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return
        paint_checkbox_indicator(painter, self._checkbox_rect(rect), self._check_state)

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self.logicalIndexAt(event.pos()) == 0:
                self._toggle_check_state()
                return True
        return super().viewportEvent(event)

    def _toggle_check_state(self) -> None:
        if self._check_state == Qt.CheckState.Checked:
            new_state = Qt.CheckState.Unchecked
        else:
            new_state = Qt.CheckState.Checked
        self.setCheckState(new_state)
        self.checkStateChanged.emit(new_state)

    def setCheckState(self, state: Qt.CheckState):
        state = coerce_check_state(state)
        if state == self._check_state:
            return
        self._check_state = state
        self.updateSection(0)

    def checkState(self) -> Qt.CheckState:
        return self._check_state

    def _checkbox_rect(self, section_rect: QRect) -> QRect:
        x = section_rect.x() + (section_rect.width() - _CHECKBOX_SIZE) // 2
        y = section_rect.y() + (section_rect.height() - _CHECKBOX_SIZE) // 2
        return QRect(x, y, _CHECKBOX_SIZE, _CHECKBOX_SIZE)
