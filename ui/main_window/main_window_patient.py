from __future__ import annotations
'''
患者页（tabWidget 的 tab2）管理
'''
import logging
from math import ceil
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QDateTime, QRect, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QIntValidator, QPalette
from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QHeaderView,
    QStyleOptionButton,
    QStyle,
    QTableWidgetItem,
    QDialog,
    QAbstractItemView,
)

from ui.core.base_table_controller import BaseTableController
from ui.core.utils import get_ui_attr, safe_connect
from ui.dialogs.patient_newa import PatientNewDialog
from ui.dialogs.tips_dialog import TipsDialog


class CheckBoxHeader(QHeaderView):
    """带复选框的表头（仅用于第1列）"""

    checkStateChanged = Signal(Qt.CheckState)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._check_state = Qt.Unchecked
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex != 0:
            return
        option = QStyleOptionButton()
        option.state |= QStyle.State_Enabled
        if self._check_state == Qt.Checked:
            option.state |= QStyle.State_On
        elif self._check_state == Qt.PartiallyChecked:
            option.state |= QStyle.State_NoChange
        else:
            option.state |= QStyle.State_Off
        option.rect = self._checkbox_rect(rect)
        self.style().drawControl(QStyle.CE_CheckBox, option, painter)

    def mousePressEvent(self, event):
        index = self.logicalIndexAt(event.pos())
        if index == 0 and self._checkbox_rect(self._section_rect(0)).contains(event.pos()):
            self._toggle_state()
            return
        super().mousePressEvent(event)

    def _toggle_state(self):
        new_state = Qt.Unchecked if self._check_state == Qt.Checked else Qt.Checked
        self.setCheckState(new_state)
        if hasattr(self, "checkStateChanged"):
            self.checkStateChanged.emit(new_state)

    def setCheckState(self, state: Qt.CheckState):
        if state == self._check_state:
            return
        self._check_state = state
        self.updateSection(0)

    def checkState(self) -> Qt.CheckState:
        return self._check_state

    def _checkbox_rect(self, section_rect) -> QRect:
        option = QStyleOptionButton()
        check_box_size = self.style().sizeFromContents(QStyle.CT_CheckBox, option, QSize(), None)
        x = section_rect.x() + (section_rect.width() - check_box_size.width()) // 2
        y = section_rect.y() + (section_rect.height() - check_box_size.height()) // 2
        return QRect(x, y, check_box_size.width(), check_box_size.height())

    def _section_rect(self, logicalIndex: int) -> QRect:
        """兼容性包装：在 PySide6 中没有 sectionRect，手动构造"""
        return QRect(
            self.sectionPosition(logicalIndex),
            0,
            self.sectionSize(logicalIndex),
            self.height(),
        )


class PatientPageController(BaseTableController):
    """患者页（tabWidget 的 tab2）管理"""

    _PAGINATION_HEIGHT = 38

    def __init__(
        self,
        parent: QWidget,
        ui,
        patient_app,
        user_app,
        logger: Optional[logging.Logger] = None,
        on_patient_selected: Optional[Callable[[dict], None]] = None,
        report_app=None,
    ):
        super().__init__(ui, table_name="tableWidget_patient_2")
        self.parent = parent
        self.patient_app = patient_app
        self.report_app = report_app  # 报告应用层
        self.user_app = user_app
        self.logger = logger or logging.getLogger(__name__)
        self._row_checkboxes: List[QCheckBox] = []
        self._header_checkbox: Optional[CheckBoxHeader] = None
        self._bulk_updating_checks = False
        self._all_patients: List[dict] = []
        self._patient_data: List[dict] = []
        self._page_index = 0
        self._page_size = 10
        self._pagination_frame: Optional[QFrame] = None
        self._table_height_adjusted = False
        self._on_patient_selected = on_patient_selected

    # ---------- 对外接口 ----------
    def bind_signals(self):
        """绑定患者页相关事件"""
        search = get_ui_attr(self.ui, "lineEdit_search")
        safe_connect(self.logger, getattr(search, "textChanged", None), self._on_search_text_changed)
        search2 = get_ui_attr(self.ui, "lineEdit_search_2")
        safe_connect(self.logger, getattr(search2, "textChanged", None), self._on_search_text_changed)
        reset_btn = get_ui_attr(self.ui, "pushButton_reset")
        safe_connect(self.logger, getattr(reset_btn, "clicked", None), self._on_reset_search)
        new_btn_tab = get_ui_attr(self.ui, "pushButton_tab1new")
        safe_connect(self.logger, getattr(new_btn_tab, "clicked", None), self._open_new_patient_dialog)
        new_btn = get_ui_attr(self.ui, "pushButton_new")
        safe_connect(self.logger, getattr(new_btn, "clicked", None), self._open_new_patient_dialog)
        # 兼容不同 UI 命名：优先新名称，回退到当前 main_window.ui 中的 pushButton
        delete_btn = get_ui_attr(self.ui, "pushButton_patient_delete") or get_ui_attr(self.ui, "pushButton")
        safe_connect(self.logger, getattr(delete_btn, "clicked", None), self._on_delete_selected_patients)

    def init_ui(self):
        """初始化表格与状态"""
        self._setup_patient_table()

    def refresh(self):
        """刷新患者数据"""
        if self._header_checkbox is None:
            self._setup_patient_table()
        else:
            self._load_patient_data(reset_page=False)

    # ---------- 内部逻辑 ----------
    def get_table(self):
        table = get_ui_attr(self.ui, "tableWidget_patient_2")
        if table is not None:
            return table
        table = get_ui_attr(self.ui, "tableWidget_patient")
        return table if table is not None else None

    def _get_patient_table(self):
        return self.get_table()

    def _setup_patient_table(self):
        table = self._get_patient_table()
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

        table.setRowCount(0)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        palette = table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F7F7F7"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#E8F1FF"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1F1F1F"))
        table.setPalette(palette)
        v_header = table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(50)
        header = table.horizontalHeader()
        if header is not None:
            header.setHighlightSections(False)
        # 支持表格多选行（除勾选框外，也可通过行选中后批量删除）
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        safe_connect(
            self.logger,
            getattr(table.selectionModel(), "selectionChanged", None),
            self._on_table_selection_changed,
        )
        self._ensure_pagination_ui()
        self._row_checkboxes = []
        self._load_patient_data(reset_page=True)

    def _ensure_pagination_ui(self) -> None:
        if self._pagination_frame is not None:
            return
        table = self._get_patient_table()
        if table is None:
            return
        tab = table.parentWidget()
        if tab is None:
            return

        pag_h = self._PAGINATION_HEIGHT
        geo = table.geometry()
        if not self._table_height_adjusted and geo.height() > pag_h + 200:
            table.setGeometry(geo.x(), geo.y(), geo.width(), geo.height() - pag_h)
            self._table_height_adjusted = True
        geo = table.geometry()

        pagination = QFrame(tab)
        pagination.setObjectName("patientPagePagination")
        pagination.setMinimumHeight(pag_h)
        pagination.setStyleSheet(
            "QFrame#patientPagePagination { background: transparent; }"
            "QLabel { color: #98A2B3; font-size: 12px; padding: 2px 0; }"
            "QPushButton {"
            "background: transparent;"
            "border: none;"
            "color: #98A2B3;"
            "font-size: 13px;"
            "padding: 0;"
            "}"
            "QPushButton:hover:enabled { color: #4B86FC; }"
            "QPushButton:disabled { color: #D7DDEA; }"
            "QLineEdit {"
            "background: #FFFFFF;"
            "border: none;"
            "border-radius: 4px;"
            "color: #8E8E93;"
            "font-size: 12px;"
            "padding: 1px 4px;"
            "}"
        )
        layout = QHBoxLayout(pagination)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)
        layout.addStretch()

        self._total_label = QLabel("共0条", pagination)
        layout.addWidget(self._total_label)

        self._prev_button = QPushButton("<", pagination)
        self._prev_button.setFixedSize(16, 24)
        self._prev_button.setCursor(Qt.PointingHandCursor)
        self._prev_button.clicked.connect(self._on_prev_page)
        layout.addWidget(self._prev_button)

        self._page_label = QLabel("0/0页", pagination)
        self._page_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._page_label)

        self._next_button = QPushButton(">", pagination)
        self._next_button.setFixedSize(16, 24)
        self._next_button.setCursor(Qt.PointingHandCursor)
        self._next_button.clicked.connect(self._on_next_page)
        layout.addWidget(self._next_button)

        layout.addSpacing(4)
        layout.addWidget(QLabel("前往", pagination))

        self._page_jump_input = QLineEdit(pagination)
        self._page_jump_input.setFixedSize(36, 20)
        self._page_jump_input.setAlignment(Qt.AlignCenter)
        self._page_jump_input.setValidator(QIntValidator(1, 9999, self._page_jump_input))
        self._page_jump_input.returnPressed.connect(self._on_jump_page)
        self._page_jump_input.editingFinished.connect(self._on_jump_page)
        layout.addWidget(self._page_jump_input)

        layout.addWidget(QLabel("页", pagination))

        self._pagination_frame = pagination
        self._layout_pagination_position()
        pagination.show()
        QTimer.singleShot(0, self._refresh_page)

    def _layout_pagination_position(self) -> None:
        """将分页器贴在表格区域右下角。"""
        if self._pagination_frame is None:
            return
        table = self._get_patient_table()
        if table is None:
            return
        geo = table.geometry()
        self._pagination_frame.adjustSize()
        content_width = self._pagination_frame.sizeHint().width()
        pag_h = max(self._PAGINATION_HEIGHT, self._pagination_frame.sizeHint().height())
        right_inset = 40
        pag_w = min(content_width, geo.width())
        pag_x = geo.x() + geo.width() - pag_w - right_inset
        pag_y = geo.y() + geo.height() + 2
        self._pagination_frame.setGeometry(pag_x, pag_y, pag_w, pag_h)

    def _recalculate_page_size(self) -> None:
        table = self._get_patient_table()
        if table is None:
            return
        v_header = table.verticalHeader()
        row_height = v_header.defaultSectionSize() if v_header is not None else 50
        viewport_h = table.viewport().height()
        if viewport_h <= 0:
            return
        page_size = max(1, viewport_h // row_height)
        if page_size != self._page_size:
            self._page_size = page_size
            self._clamp_page_index()

    def _total_pages(self) -> int:
        if not self._all_patients:
            return 0
        return int(ceil(len(self._all_patients) / self._page_size))

    def _clamp_page_index(self) -> None:
        total_pages = self._total_pages()
        if total_pages <= 0:
            self._page_index = 0
            return
        self._page_index = min(max(self._page_index, 0), total_pages - 1)

    def _update_pagination(self) -> None:
        if self._pagination_frame is None:
            return
        total = len(self._all_patients)
        total_pages = self._total_pages()
        current_page = 0 if total_pages == 0 else self._page_index + 1
        self._total_label.setText(f"共{total}条")
        self._page_label.setText(f"{current_page}/{total_pages}页")
        self._page_jump_input.setText("" if total_pages == 0 else str(current_page))
        self._page_jump_input.setEnabled(total_pages > 0)
        self._prev_button.setEnabled(self._page_index > 0)
        self._next_button.setEnabled(total_pages > 0 and self._page_index < total_pages - 1)
        self._layout_pagination_position()

    def _refresh_page(self) -> None:
        table = self._get_patient_table()
        if table is None:
            return
        self._recalculate_page_size()
        self._clamp_page_index()
        start = self._page_index * self._page_size
        end = start + self._page_size
        page_patients = self._all_patients[start:end]
        self._populate_patient_table(table, page_patients)
        self._update_pagination()

    def _on_prev_page(self) -> None:
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self._refresh_page()

    def _on_next_page(self) -> None:
        total_pages = self._total_pages()
        if total_pages == 0 or self._page_index >= total_pages - 1:
            return
        self._page_index += 1
        self._refresh_page()

    def _on_jump_page(self) -> None:
        total_pages = self._total_pages()
        if total_pages == 0:
            return
        text = self._page_jump_input.text().strip()
        try:
            page = int(text)
        except ValueError:
            self._update_pagination()
            return
        self._page_index = min(max(page, 1), total_pages) - 1
        self._refresh_page()

    def _fetch_patients(self) -> List[dict]:
        keyword = ""
        for name in ("lineEdit_search_2", "lineEdit_search"):
            edit = get_ui_attr(self.ui, name)
            if edit is not None:
                keyword = edit.text().strip()
                if keyword:
                    break
        try:
            if keyword:
                return list(self.patient_app.search_patients(keyword) or [])
            return list(self.patient_app.get_patients() or [])
        except Exception as e:
            self.logger.error(f"加载患者数据失败: {e}")
            TipsDialog.show_tips(self.parent, f"加载患者数据失败: {e}")
            return []

    def _load_patient_data(self, *, reset_page: bool = False):
        if reset_page:
            self._page_index = 0
        self._all_patients = self._fetch_patients()
        self._refresh_page()

    def _populate_patient_table(self, table, patients: List[dict]):
        table.blockSignals(True)
        self.clear_table()
        self._row_checkboxes = []

        if not patients:
            table.blockSignals(False)
            self._patient_data = []
            self._set_header_check_state(Qt.CheckState.Unchecked)
            return

        table.setRowCount(len(patients))
        self._patient_data = list(patients)

        for row, patient in enumerate(patients):
            self.set_text_item(row, 1, patient.get("Name"))
            self.set_text_item(row, 2, patient.get("Sex"))

            age = patient.get("Age")
            age_text = "" if age is None else str(age)
            self.set_text_item(row, 3, age_text)

            self.set_text_item(row, 4, patient.get("PatientId"))
            self.set_text_item(row, 5, patient.get("VisitTime"))

            self._setup_patient_row_widgets(table, row)

        table.blockSignals(False)
        self._update_header_check_state()

    def _selected_rows(self, table) -> set[int]:
        model = table.selectionModel()
        if model is None:
            return set()
        return {idx.row() for idx in model.selectedRows()}

    def _row_widget_background(self, table, row: int) -> str:
        if row in self._selected_rows(table):
            return "#E8F1FF"
        return "#F7F7F7" if row % 2 == 1 else "#FFFFFF"

    def _apply_widget_background(self, widget: QWidget, row: int, col: int, bg: str) -> None:
        """用 objectName 限定样式，只给容器上色，不影响 QCheckBox / 按钮。"""
        object_name = f"patient_cell_wrap_{row}_{col}"
        widget.setObjectName(object_name)
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setStyleSheet(f"QWidget#{object_name} {{ background-color: {bg}; }}")

    def _sync_widget_row_background(self, table, row: int) -> None:
        bg = self._row_widget_background(table, row)
        for col in range(table.columnCount()):
            widget = table.cellWidget(row, col)
            if widget is not None:
                self._apply_widget_background(widget, row, col, bg)

    def _on_table_selection_changed(self, selected, deselected) -> None:
        table = self._get_patient_table()
        if table is None:
            return
        changed_rows = set()
        for index in list(selected.indexes()) + list(deselected.indexes()):
            changed_rows.add(index.row())
        for row in changed_rows:
            self._sync_widget_row_background(table, row)

    def _setup_patient_row_widgets(self, table, row: int):
        checkbox = QCheckBox()
        checkbox.setTristate(False)
        checkbox.setStyleSheet(
            "QCheckBox { background: transparent; spacing: 4px; }"
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        checkbox.stateChanged.connect(lambda state, r=row: self._on_row_checkbox_changed(r, state))
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.addWidget(checkbox)
        table.setCellWidget(row, 0, cb_container)
        self._row_checkboxes.append(checkbox)

        view_btn = QPushButton("查看")
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.setFlat(True)
        view_btn.setStyleSheet(
            "QPushButton {"
            "    color: #4B86FC;"
            "    text-decoration: underline;"
            "    background: transparent;"
            "    border: none;"
            "    font-size: 20px;"
            "}"
            "QPushButton:pressed {"
            "    color: #2f64c8;"
            "}"
        )
        view_btn.clicked.connect(lambda checked, r=row: self._on_view_treat_record_clicked(r))
        view_container = QWidget()
        view_layout = QHBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setAlignment(Qt.AlignCenter)
        view_layout.addWidget(view_btn)
        if table.columnCount() > 6:
            table.setCellWidget(row, 6, view_container)

        edit_btn = QPushButton("编辑")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFlat(True)
        edit_btn.setStyleSheet(
            "QPushButton {"
            "    color: #4B86FC;"
            "    text-decoration: underline;"
            "    background: transparent;"
            "    border: none;"
            "    font-size: 20px;"
            "}"
            "QPushButton:pressed {"
            "    color: #2f64c8;"
            "}"
        )
        edit_btn.clicked.connect(lambda checked, r=row: self._on_edit_patient_clicked(r))

        op_container = QWidget()
        op_layout = QHBoxLayout(op_container)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setSpacing(0)
        op_layout.setAlignment(Qt.AlignCenter)
        op_layout.addWidget(edit_btn)
        if table.columnCount() > 7:
            table.setCellWidget(row, 7, op_container)

        self._sync_widget_row_background(table, row)

    def _on_view_treat_record_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        patient = self._patient_data[row]
        open_records = getattr(self.parent, "open_patient_treat_records", None)
        if callable(open_records):
            open_records(patient)
            return
        TipsDialog.show_tips(self.parent, "无法打开诊疗记录模块")

    def _on_edit_patient_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        patient = self._patient_data[row]
        dialog = PatientNewDialog(self.parent, data=patient, is_edit=True)
        if dialog.exec() != QDialog.Accepted:
            return

        updated = dialog.get_data()
        merged = {**patient, **updated}
        merged["PatientId"] = patient.get("PatientId", "")
        if self.user_app and self.user_app.current_user:
            merged["UserId"] = self.user_app.current_user.get("UserName", "")

        try:
            ok = self.patient_app.update_patient(merged)
        except Exception as e:
            self.logger.error(f"更新患者异常: {e}")
            TipsDialog.show_tips(self.parent, f"更新患者失败: {e}")
            return

        if ok:
            TipsDialog.show_tips(self.parent, "更新患者成功")
            self.refresh()
        else:
            TipsDialog.show_tips(self.parent, "更新患者失败")

    def _on_delete_patient_clicked(self, row: int):
        if not self._patient_data or row >= len(self._patient_data):
            TipsDialog.show_tips(self.parent, "无法获取患者信息")
            return

        self._delete_patients([self._patient_data[row]])

    def _on_delete_selected_patients(self):
        patients = self._get_checked_patients()
        if not patients:
            patients = self._get_row_selected_patients()
        if not patients:
            TipsDialog.show_tips(self.parent, "请先勾选或选中需要删除的患者")
            return

        self._delete_patients(patients)

    def _get_checked_patients(self) -> List[dict]:
        checked_patients: List[dict] = []
        for row, checkbox in enumerate(self._row_checkboxes):
            if row >= len(self._patient_data):
                break
            if checkbox.checkState() == Qt.CheckState.Checked:
                checked_patients.append(self._patient_data[row])
        return checked_patients

    def _get_row_selected_patients(self) -> List[dict]:
        """读取表格当前选中行对应的患者，支持 Ctrl/Shift 多选。"""
        table = self._get_patient_table()
        if table is None:
            return []
        selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
        patients: List[dict] = []
        for row in selected_rows:
            if 0 <= row < len(self._patient_data):
                patients.append(self._patient_data[row])
        return patients

    def _delete_patients(self, patients: List[dict]) -> None:
        valid_patients = []
        for patient in patients:
            patient_id = str(patient.get("PatientId", "") or "").strip()
            if patient_id:
                valid_patients.append(patient)

        if not valid_patients:
            TipsDialog.show_tips(self.parent, "所选患者病历号为空，无法删除")
            return

        if len(valid_patients) == 1:
            patient = valid_patients[0]
            patient_id = patient.get("PatientId", "")
            patient_name = patient.get("Name", "")
            message = f"确定删除患者「{patient_name or patient_id}」及其诊疗记录？"
        else:
            message = f"确定删除选中的 {len(valid_patients)} 位患者及其诊疗记录？"

        parent_win = self.parent.window() if self.parent else None
        if not TipsDialog.show_confirm(parent_win, message):
            return

        success_ids: List[str] = []
        failed_names: List[str] = []
        for patient in valid_patients:
            patient_id = str(patient.get("PatientId", "") or "").strip()
            patient_name = str(patient.get("Name", "") or patient_id).strip()
            try:
                ok = self.patient_app.delete_patient(patient_id)
            except Exception as e:
                self.logger.error(f"删除患者异常: {e}")
                ok = False
            if ok:
                success_ids.append(patient_id)
                host = self.parent
                if hasattr(host, "clear_treat_context_if_patient_removed"):
                    try:
                        host.clear_treat_context_if_patient_removed(patient_id)
                    except Exception:
                        self.logger.exception("删除患者后清理当前治疗选择失败")
            else:
                failed_names.append(patient_name)

        self.refresh()

        if failed_names and success_ids:
            TipsDialog.show_tips(
                self.parent,
                f"已删除 {len(success_ids)} 位患者，以下删除失败：{', '.join(failed_names)}",
            )
        elif failed_names:
            TipsDialog.show_tips(
                self.parent,
                f"删除失败：{', '.join(failed_names)}",
            )
        else:
            TipsDialog.show_tips(self.parent, f"已删除 {len(success_ids)} 位患者")

    def _open_new_patient_dialog(self):
        dialog = PatientNewDialog(self.parent, patient_app=self.patient_app)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        if self.user_app and self.user_app.current_user:
            user_name = self.user_app.current_user.get("UserName", "")
            data.setdefault("UserId", user_name)
        if not data.get("VisitTime"):
            data["VisitTime"] = QDateTime.currentDateTime().toString("yyyy/MM/dd HH:mm:ss")

        patient_id = str(data.get("PatientId", "") or "").strip()
        try:
            ok = self.patient_app.add_patient(data)
        except Exception as e:
            self.logger.error(f"新增患者异常: {e}")
            TipsDialog.show_tips(self.parent, f"新增患者失败: {e}")
            return

        if ok:
            TipsDialog.show_tips(self.parent, "新增患者成功")
            self.refresh()
            saved = self.patient_app.get_patient_by_id(patient_id) if patient_id else None
            if callable(self._on_patient_selected):
                self._on_patient_selected(saved or data)
        else:
            TipsDialog.show_tips(self.parent, "新增患者失败")

    def _on_row_checkbox_changed(self, row: int, state: int):
        if self._bulk_updating_checks:
            return
        self._update_header_check_state()

    def _update_header_check_state(self):
        if self._header_checkbox is None:
            return
        if not self._row_checkboxes:
            self._set_header_check_state(Qt.CheckState.Unchecked)
            return

        total = len(self._row_checkboxes)
        checked = sum(cb.checkState() == Qt.CheckState.Checked for cb in self._row_checkboxes)
        unchecked = sum(cb.checkState() == Qt.CheckState.Unchecked for cb in self._row_checkboxes)

        if checked == total:
            state = Qt.CheckState.Checked
        elif unchecked == total:
            state = Qt.CheckState.Unchecked
        else:
            state = Qt.CheckState.PartiallyChecked

        self._set_header_check_state(state)

    def _set_header_check_state(self, state: Qt.CheckState) -> None:
        if self._header_checkbox is None:
            return
        self._bulk_updating_checks = True
        self._header_checkbox.setCheckState(state)
        self._bulk_updating_checks = False

    def _on_header_checkbox_state_changed(self, state: Qt.CheckState):
        if self._bulk_updating_checks:
            return
        if state not in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
            return
        self._bulk_updating_checks = True
        for cb in self._row_checkboxes:
            cb.setCheckState(Qt.CheckState.Checked if state == Qt.CheckState.Checked else Qt.CheckState.Unchecked)
        self._bulk_updating_checks = False

    def _on_search_text_changed(self, text: str):
        keyword = text.strip() if text else ""
        patients: List[dict] = []
        try:
            if keyword:
                patients = self.patient_app.search_patients(keyword)
            else:
                patients = self.patient_app.get_patients()
        except Exception as e:
            self.logger.error(f"搜索患者失败: {e}")
            TipsDialog.show_tips(self.parent, f"搜索患者失败: {e}")
            patients = []

        self._page_index = 0
        self._all_patients = list(patients)
        self._refresh_page()

    def _on_reset_search(self):
        line_edit = get_ui_attr(self.ui, "lineEdit_search")
        if line_edit:
            line_edit.clear()
        line_edit_2 = get_ui_attr(self.ui, "lineEdit_search_2")
        if line_edit_2:
            line_edit_2.clear()
        self._load_patient_data(reset_page=True)
