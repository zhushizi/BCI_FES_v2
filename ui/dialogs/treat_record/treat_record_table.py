"""
诊疗记录表格渲染与交互逻辑。
"""

from __future__ import annotations

from typing import Callable, Iterable, Tuple

from PySide6.QtCore import Qt, QRect, QEvent, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidgetItem,
    QWidget,
    QHeaderView,
)

from ui.core.table_utils import set_text_item
from ui.core.utils import get_ui_attr, safe_connect

_CHECKBOX_CHECKED_COLOR = "#789EFF"
_CHECKBOX_UNCHECKED_BORDER = "#D0D5DD"
_CHECKBOX_SIZE = 18


def _coerce_check_state(state) -> Qt.CheckState:
    if isinstance(state, Qt.CheckState):
        return state
    return Qt.CheckState(int(state))


def _check_state_value(state: Qt.CheckState) -> int:
    state = _coerce_check_state(state)
    return state.value


def _paint_checkbox_indicator(painter: QPainter, rect: QRect, state: Qt.CheckState) -> None:
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


class ReportCheckBox(QWidget):
    """自绘复选框，与表头样式一致（避免系统样式下勾选标记不显示）。"""

    stateChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = Qt.CheckState.Unchecked
        self.setFixedSize(_CHECKBOX_SIZE, _CHECKBOX_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def checkState(self) -> Qt.CheckState:
        return self._state

    def setCheckState(self, state: Qt.CheckState) -> None:
        state = _coerce_check_state(state)
        if state == self._state:
            return
        self._state = state
        self.update()
        self.stateChanged.emit(_check_state_value(state))

    def setChecked(self, checked: bool) -> None:
        self.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        _paint_checkbox_indicator(painter, self.rect(), self._state)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = (
                Qt.CheckState.Unchecked
                if self._state == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            self.setCheckState(new_state)
        super().mousePressEvent(event)


class CheckBoxHeader(QHeaderView):
    """与 tab_patient 一致的表头复选框实现（第 0 列）。"""

    checkStateChanged = Signal(Qt.CheckState)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._check_state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return
        _paint_checkbox_indicator(painter, self._checkbox_rect(rect), self._check_state)

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
        state = _coerce_check_state(state)
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

    def _section_rect(self, logical_index: int) -> QRect:
        return QRect(
            self.sectionViewportPosition(logical_index),
            0,
            self.sectionSize(logical_index),
            self.height(),
        )


class TreatRecordTable:
    def __init__(self, ui, logger):
        self.ui = ui
        self._logger = logger
        self._block_item_changed = False
        self._bulk_updating_checks = False
        self._row_checkboxes: list[ReportCheckBox | None] = []
        self._header_checkbox: CheckBoxHeader | None = None

    def _get_table(self):
        return get_ui_attr(self.ui, "tableWidget_treatrecord")

    def setup_header_checkbox(self) -> None:
        table = self._get_table()
        if table is None:
            return
        column_count = table.columnCount()
        if column_count == 0:
            return
        old_header = table.horizontalHeader()
        section_sizes = [old_header.sectionSize(i) for i in range(column_count)]
        default_section_size = old_header.defaultSectionSize()
        stretch_last = old_header.stretchLastSection()

        header = CheckBoxHeader(table)
        header.setDefaultSectionSize(default_section_size)
        for idx, size in enumerate(section_sizes):
            header.resizeSection(idx, size)
        header.setStretchLastSection(stretch_last)
        table.setHorizontalHeader(header)
        self._header_checkbox = header
        header.checkStateChanged.connect(self._on_header_checkbox_state_changed)

        for col in range(column_count):
            item = table.horizontalHeaderItem(col)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(col, item)
            item.setTextAlignment(Qt.AlignCenter)

    def bind_header_click(self) -> None:
        # 自绘表头在 mousePressEvent 内部处理点击并发出 checkStateChanged；
        # 这里保留接口，避免调用方改动。
        return

    def load_records(
        self,
        records: Iterable[dict],
        on_view_clicked: Callable[[int], None],
        patient_name: str = "",
    ) -> None:
        table = self._get_table()
        if table is None:
            return

        table.setRowCount(0)
        self._row_checkboxes = []
        self._block_item_changed = True

        # 会话行不含患者姓名，仅 PatientId；姓名由外层传入（与表头「患者姓名」一致）
        display_name = (patient_name or "").strip() or ""

        for record in records:
            row = table.rowCount()
            table.insertRow(row)
            self._set_checkbox_item(table, row, 0)
            name_text = display_name or str(record.get("PatientId", "") or "")
            item_name = set_text_item(table, row, 1, name_text)
            try:
                item_name.setData(Qt.UserRole, record.get("SessionId"))
            except Exception:
                pass
            set_text_item(table, row, 2, record.get("Paradigm", ""))
            set_text_item(table, row, 3, self._map_scheme_name(record.get("StimSchemeAB", "")))
            set_text_item(table, row, 4, self._map_stim_position(record.get("StimPosition", "")))
            set_text_item(table, row, 5, self._map_stim_interval(record.get("StimFreqAB", "")))
            set_text_item(table, row, 6, record.get("TotalTrainDuration", ""))
            set_text_item(table, row, 7, record.get("UpdateTime", ""))
            self._set_action_button(table, row, 8, on_view_clicked)

        self._block_item_changed = False
        self.update_header_check_state()

    @staticmethod
    def _map_stim_position(value) -> str:
        text = str(value or "").strip()
        if text.lower() == "gou":
            return "小腿"
        if text.lower() == "tai":
            return "大腿"
        return text

    @staticmethod
    def _map_scheme_name(value) -> str:
        text = str(value or "").strip()
        if text == "0":
            return "方案一"
        if text == "1":
            return "方案二"
        return text

    @staticmethod
    def _map_stim_interval(value) -> str:
        text = str(value or "").strip()
        try:
            n = int(text)
            if 20 <= n <= 100:
                return f"{n} ms"
        except (TypeError, ValueError):
            pass
        mapping = {
            "0": "0.5",
            "1": "0.6",
            "2": "0.7",
            "3": "0.8",
            "4": "0.9",
            "5": "1.0",
            "6": "2.0",
            "7": "3.0",
            "8": "4.0",
            "9": "5.0",
        }
        return mapping.get(text, text)

    def get_selected_session_ids(self) -> Tuple[list[int], list[int]]:
        table = self._get_table()
        if table is None:
            return [], []

        rows_to_delete: list[int] = []
        session_ids: list[int] = []
        for row, checkbox in enumerate(self._row_checkboxes):
            if checkbox and checkbox.checkState() == Qt.CheckState.Checked:
                pid_item = table.item(row, 1)
                session_id = None
                if pid_item is not None:
                    session_id = pid_item.data(Qt.UserRole)
                if session_id:
                    rows_to_delete.append(row)
                    session_ids.append(session_id)
        return rows_to_delete, session_ids

    def remove_rows(self, rows: Iterable[int]) -> None:
        table = self._get_table()
        if table is None:
            return
        for row in sorted(rows, reverse=True):
            table.removeRow(row)
            if row < len(self._row_checkboxes):
                self._row_checkboxes.pop(row)
        self.update_header_check_state()

    def extract_row_data(self, row: int) -> tuple[dict, str | None, int | None]:
        table = self._get_table()
        if table is None:
            return {}, None, None
        record_data: dict = {}
        treat_start_time = None
        session_id = None
        for col in range(1, 8):
            item = table.item(row, col)
            if item:
                header_item = table.horizontalHeaderItem(col)
                if header_item:
                    header_text = header_item.text()
                    record_data[header_text] = item.text()
                    if header_text == "治疗时间":
                        treat_start_time = item.text()
        item_pid = table.item(row, 1)
        if item_pid is not None:
            try:
                session_id = item_pid.data(Qt.UserRole)
            except Exception:
                session_id = None
        return record_data, treat_start_time, session_id

    def update_header_check_state(self) -> None:
        if self._header_checkbox is None or self._bulk_updating_checks:
            return
        active_checkboxes = [cb for cb in self._row_checkboxes if cb is not None]
        row_count = len(active_checkboxes)
        if row_count == 0:
            self._bulk_updating_checks = True
            self._header_checkbox.setCheckState(Qt.CheckState.Unchecked)
            self._bulk_updating_checks = False
            return
        checked = sum(cb.checkState() == Qt.CheckState.Checked for cb in active_checkboxes)
        unchecked = sum(cb.checkState() == Qt.CheckState.Unchecked for cb in active_checkboxes)
        self._bulk_updating_checks = True
        if checked == row_count:
            self._header_checkbox.setCheckState(Qt.CheckState.Checked)
        elif unchecked == row_count:
            self._header_checkbox.setCheckState(Qt.CheckState.Unchecked)
        else:
            self._header_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        self._bulk_updating_checks = False

    def _on_header_checkbox_state_changed(self, state: Qt.CheckState) -> None:
        if self._bulk_updating_checks:
            return
        state = _coerce_check_state(state)
        if state not in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
            return
        target = Qt.CheckState.Checked if state == Qt.CheckState.Checked else Qt.CheckState.Unchecked
        self._bulk_updating_checks = True
        self._block_item_changed = True
        for checkbox in self._row_checkboxes:
            if checkbox is None:
                continue
            checkbox.blockSignals(True)
            checkbox.setCheckState(target)
            checkbox.blockSignals(False)
        self._block_item_changed = False
        self._bulk_updating_checks = False

    def _on_row_checkbox_changed(self, row: int, state: int) -> None:
        if self._block_item_changed:
            return
        self.update_header_check_state()

    def _set_checkbox_item(self, table, row: int, col: int) -> None:
        checkbox = ReportCheckBox()
        checkbox.stateChanged.connect(lambda state, r=row: self._on_row_checkbox_changed(r, state))
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(checkbox)
        table.setCellWidget(row, col, container)
        while len(self._row_checkboxes) <= row:
            self._row_checkboxes.append(None)
        self._row_checkboxes[row] = checkbox

    def _set_action_button(
        self,
        table,
        row: int,
        col: int,
        on_view_clicked: Callable[[int], None],
    ) -> None:
        btn_view = QPushButton("查看")
        btn_view.setCursor(Qt.PointingHandCursor)
        btn_view.setStyleSheet("color: #4B86FC; background: transparent; border: none;")
        btn_view.clicked.connect(lambda checked, r=row: on_view_clicked(r))

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        layout.addWidget(btn_view, alignment=Qt.AlignCenter)
        layout.addStretch()
        table.setCellWidget(row, col, container)
