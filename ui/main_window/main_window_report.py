from __future__ import annotations

import csv
import logging
from math import ceil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QFile, QIODevice, Qt, Signal
from PySide6.QtGui import QIntValidator, QColor, QPalette
from PySide6.QtUiTools import QUiLoader
from ui.core.dialog_overlay import get_save_file_name
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.core.resource_loader import ensure_resources_loaded
from ui.core.table_utils import set_text_item
from ui.core.utils import get_ui_attr, safe_connect
from ui.dialogs.record_compare import RecordCompareDialog
from ui.dialogs.tips_dialog import TipsDialog
from ui.dialogs.treat_record.treat_record_actions import TreatRecordActions
from ui.dialogs.treat_record.treat_record_table import TreatRecordTable

UI_ROOT = Path(__file__).resolve().parents[1]
TREAT_RECORD_UI_PATH = UI_ROOT / "treat_record.ui"


class ReportPatientsPanel(QWidget):
    patient_selected = Signal(dict)
    export_clicked = Signal()
    delete_clicked = Signal()

    _PAGINATION_HEIGHT = 38

    def __init__(self, patient_app, logger: logging.Logger, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.patient_app = patient_app
        self._logger = logger
        self._all_patients: list[dict] = []
        self._selected_patient_id: Optional[str] = None
        self._page_index = 0
        self._page_size = 8
        self._build_ui()
        self.refresh()

    def select_patient_by_id(
        self,
        patient_id: str,
        *,
        clear_search: bool = True,
    ) -> Optional[dict]:
        """选中指定患者并刷新列表（可选清空搜索框）。"""
        pid = str(patient_id or "").strip()
        if not pid:
            return None
        if clear_search:
            prev = self._search_input.blockSignals(True)
            self._search_input.clear()
            self._search_input.blockSignals(prev)
        return self.refresh(selected_patient_id=pid, reset_page=False)

    def refresh(self, selected_patient_id: Optional[str] = None, *, reset_page: bool = False) -> Optional[dict]:
        if selected_patient_id is not None:
            self._selected_patient_id = str(selected_patient_id or "").strip() or None
        if reset_page:
            self._page_index = 0

        keyword = self._search_input.text().strip()
        try:
            if keyword:
                self._all_patients = list(self.patient_app.search_patients(keyword) or [])
            else:
                self._all_patients = list(self.patient_app.get_patients() or [])
        except Exception:
            self._logger.exception("加载报表页患者列表失败")
            self._all_patients = []

        if selected_patient_id is not None:
            self._sync_page_to_selected()
        else:
            self._clamp_page_index()
        return self._refresh_page()

    def current_patient(self) -> Optional[dict]:
        patient_id = self._selected_patient_id
        if not patient_id:
            return None
        for patient in self._all_patients:
            if self._patient_key(patient) == patient_id:
                return patient
        return None

    def _build_ui(self) -> None:
        self.setObjectName("reportPatientsPanel")
        self.setStyleSheet(
            "QWidget#reportPatientsPanel {"
            "background: #FFFFFF;"
            "border: 2px solid #4B86FC;"
            "border-radius: 16px;"
            "}"
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(10)

        search_wrap = QFrame()
        search_wrap.setStyleSheet(
            "QFrame {"
            "background: #F7F8FC;"
            "border: 1px solid #E9EDF5;"
            "border-radius: 12px;"
            "}"
        )
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setFrame(False)
        self._search_input.setPlaceholderText("请输入关键字")
        self._search_input.setStyleSheet(
            "QLineEdit {"
            "background: transparent;"
            "border: none;"
            "font-size: 13px;"
            "color: #1F1F1F;"
            "}"
        )
        safe_connect(self._logger, self._search_input.textChanged, self._on_search_text_changed)
        search_layout.addWidget(self._search_input, 1)

        search_icon = QLabel()
        search_icon.setFixedSize(16, 16)
        search_icon.setStyleSheet("border-image: url(:/treat/pic/treat_search.png);")
        search_layout.addWidget(search_icon)
        top_bar.addWidget(search_wrap, 1)

        export_btn = QPushButton()
        export_btn.setFixedSize(71, 41)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setText("导出")
        export_btn.setStyleSheet(
            "QPushButton {"
            "background: transparent;"
            "border: 1px solid #4B86FC;"
            "border-radius: 10px;"
            "color: #4B86FC;"
            "padding: 6px 12px;"
            "}"
            "QPushButton:hover { background: rgba(75,134,252,0.08); }"
            "QPushButton:pressed { background: rgba(75,134,252,0.16); }"
        )
        safe_connect(self._logger, export_btn.clicked, self.export_clicked.emit)
        top_bar.addWidget(export_btn)

        delete_btn = QPushButton()
        delete_btn.setFixedSize(71, 41)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setText("删除")
        delete_btn.setStyleSheet(
            "QPushButton {"
            "background: transparent;"
            "border: 1px solid #F04438;"
            "border-radius: 10px;"
            "color: #F04438;"
            "padding: 6px 12px;"
            "}"
            "QPushButton:hover { background: rgba(240,68,56,0.08); }"
            "QPushButton:pressed { background: rgba(240,68,56,0.16); }"
        )
        safe_connect(self._logger, delete_btn.clicked, self.delete_clicked.emit)
        top_bar.addWidget(delete_btn)

        root_layout.addLayout(top_bar)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["序号", "姓名", "就诊日期"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        palette = self._table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F7F7F7"))
        self._table.setPalette(palette)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultSectionSize(100)
        self._table.horizontalHeader().resizeSection(0, 70)
        self._table.horizontalHeader().resizeSection(1, 110)
        self._table.verticalHeader().setDefaultSectionSize(44)
        self._table.setStyleSheet(
            "QTableWidget {"
            "border: none;"
            "background: #FFFFFF;"
            "alternate-background-color: #F7F7F7;"
            "gridline-color: transparent;"
            "}"
            "QHeaderView::section {"
            "background: #EDF3FF;"
            "color: #929292;"
            "border: none;"
            "padding: 8px;"
            "font-size: 15px;"
            "}"
            "QTableWidget::item {"
            "border: none;"
            "padding: 6px;"
            "color: #7A7A7A;"
            "}"
            "QTableWidget::item:selected {"
            "background: #EEF4FF;"
            "color: #4B86FC;"
            "}"
        )
        safe_connect(self._logger, self._table.cellClicked, self._on_row_clicked)
        root_layout.addWidget(self._table, 1)

        pagination = QFrame(self)
        pagination.setObjectName("reportPatientPagination")
        pagination.setMinimumHeight(self._PAGINATION_HEIGHT)
        pagination.setStyleSheet(
            "QFrame#reportPatientPagination { background: transparent; }"
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
        pagination_layout = QHBoxLayout(pagination)
        pagination_layout.setContentsMargins(0, 4, 0, 4)
        pagination_layout.setSpacing(6)
        pagination_layout.setAlignment(Qt.AlignVCenter)
        pagination_layout.addStretch()

        self._total_label = QLabel("共0条", pagination)
        pagination_layout.addWidget(self._total_label)

        self._prev_button = QPushButton("<", pagination)
        self._prev_button.setFixedSize(16, 24)
        self._prev_button.setCursor(Qt.PointingHandCursor)
        self._prev_button.clicked.connect(self._on_prev_page)
        pagination_layout.addWidget(self._prev_button)

        self._page_label = QLabel("0/0页", pagination)
        self._page_label.setAlignment(Qt.AlignCenter)
        pagination_layout.addWidget(self._page_label)

        self._next_button = QPushButton(">", pagination)
        self._next_button.setFixedSize(16, 24)
        self._next_button.setCursor(Qt.PointingHandCursor)
        self._next_button.clicked.connect(self._on_next_page)
        pagination_layout.addWidget(self._next_button)

        pagination_layout.addSpacing(4)
        pagination_layout.addWidget(QLabel("前往", pagination))

        self._page_jump_input = QLineEdit(pagination)
        self._page_jump_input.setFixedSize(36, 20)
        self._page_jump_input.setAlignment(Qt.AlignCenter)
        self._page_jump_input.setValidator(QIntValidator(1, 9999, self._page_jump_input))
        self._page_jump_input.returnPressed.connect(self._on_jump_page)
        self._page_jump_input.editingFinished.connect(self._on_jump_page)
        pagination_layout.addWidget(self._page_jump_input)

        pagination_layout.addWidget(QLabel("页", pagination))
        root_layout.addWidget(pagination)

    def _page_patients(self) -> list[dict]:
        start = self._page_index * self._page_size
        end = start + self._page_size
        return self._all_patients[start:end]

    def _recalculate_page_size(self) -> None:
        row_height = self._table.verticalHeader().defaultSectionSize()
        viewport_h = self._table.viewport().height()
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

    def _sync_page_to_selected(self) -> None:
        if not self._selected_patient_id:
            self._clamp_page_index()
            return
        for index, patient in enumerate(self._all_patients):
            if self._patient_key(patient) == self._selected_patient_id:
                self._page_index = index // self._page_size
                break
        self._clamp_page_index()

    def _update_pagination(self) -> None:
        total = len(self._all_patients)
        total_pages = self._total_pages()
        current_page = 0 if total_pages == 0 else self._page_index + 1
        self._total_label.setText(f"共{total}条")
        self._page_label.setText(f"{current_page}/{total_pages}页")
        self._page_jump_input.setText("" if total_pages == 0 else str(current_page))
        self._page_jump_input.setEnabled(total_pages > 0)
        self._prev_button.setEnabled(self._page_index > 0)
        self._next_button.setEnabled(total_pages > 0 and self._page_index < total_pages - 1)

    def _refresh_page(self) -> Optional[dict]:
        self._recalculate_page_size()
        self._clamp_page_index()
        return self._populate_table()

    def _populate_table(self) -> Optional[dict]:
        page_patients = self._page_patients()
        start = self._page_index * self._page_size

        self._table.blockSignals(True)
        self._table.setRowCount(len(page_patients))

        selected_row = -1
        for row, patient in enumerate(page_patients):
            index_text = f"{start + row + 1:02d}"
            set_text_item(self._table, row, 0, index_text)
            name_item = set_text_item(self._table, row, 1, patient.get("Name", ""))
            name_item.setData(Qt.UserRole, patient)
            set_text_item(self._table, row, 2, self._format_visit_time(patient.get("VisitTime", "")))
            if self._patient_key(patient) == self._selected_patient_id:
                selected_row = row

        if selected_row < 0 and page_patients:
            selected_row = 0
            self._selected_patient_id = self._patient_key(page_patients[0])

        self._table.clearSelection()
        selected_patient = None
        if 0 <= selected_row < len(page_patients):
            self._table.selectRow(selected_row)
            selected_patient = page_patients[selected_row]
        self._table.blockSignals(False)
        self._update_pagination()
        return selected_patient

    def _on_prev_page(self) -> None:
        if self._page_index <= 0:
            return
        self._page_index -= 1
        selected = self._refresh_page()
        if selected is not None:
            self.patient_selected.emit(selected)

    def _on_next_page(self) -> None:
        total_pages = self._total_pages()
        if total_pages == 0 or self._page_index >= total_pages - 1:
            return
        self._page_index += 1
        selected = self._refresh_page()
        if selected is not None:
            self.patient_selected.emit(selected)

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
        selected = self._refresh_page()
        if selected is not None:
            self.patient_selected.emit(selected)

    def _on_search_text_changed(self, _text: str) -> None:
        self._page_index = 0
        self.refresh()

    def _on_row_clicked(self, row: int, _column: int) -> None:
        page_patients = self._page_patients()
        if not (0 <= row < len(page_patients)):
            return
        patient = page_patients[row]
        self._selected_patient_id = self._patient_key(patient)
        self.patient_selected.emit(patient)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        old_page_size = self._page_size
        self._recalculate_page_size()
        if self._page_size != old_page_size:
            self._refresh_page()

    @staticmethod
    def _format_visit_time(value: object) -> str:
        text = str(value or "").strip()
        return text.replace("/", "-")

    @staticmethod
    def _patient_key(patient: Optional[dict]) -> Optional[str]:
        if not patient:
            return None
        text = str(patient.get("PatientId") or patient.get("Name") or "").strip()
        return text or None


class EmbeddedTreatRecordPanel(QWidget):
    _PAGINATION_HEIGHT = 38
    _HEADER_HEIGHT = 71

    def __init__(self, session_app, report_app, logger: logging.Logger, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        ensure_resources_loaded()
        self._logger = logger
        self._session_app = session_app
        self._report_app = report_app
        self._patient_id = ""
        self._patient_name = ""
        self._all_records: list[dict] = []
        self._filtered_records: list[dict] = []
        self._page_index = 0
        self._page_size = 10
        self._pagination_frame: Optional[QFrame] = None
        self._actions: Optional[TreatRecordActions] = None

        loader = QUiLoader()
        ui_file = QFile(str(TREAT_RECORD_UI_PATH))
        if not ui_file.open(QIODevice.ReadOnly):
            raise FileNotFoundError(f"无法打开 UI 文件: {TREAT_RECORD_UI_PATH}")
        self.ui = loader.load(ui_file, self)
        ui_file.close()
        if self.ui is None:
            raise RuntimeError(f"无法加载 UI 文件: {TREAT_RECORD_UI_PATH}")

        self._setup_panel_background(parent)
        self.ui.setMinimumSize(0, 0)
        self.ui.setMaximumSize(16777215, 16777215)
        self.ui.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ui)

        self._table = TreatRecordTable(self.ui, self._logger)
        self._table.setup_header_checkbox()
        self._setup_record_table_background()
        self._build_header_controls()
        self._setup_connections()
        self.clear_records()

    def set_patient(self, patient: Optional[dict]) -> None:
        if not patient:
            self._patient_id = ""
            self._patient_name = ""
            self._actions = None
            self.clear_records()
            return

        self._patient_id = str(patient.get("PatientId", "") or "").strip()
        self._patient_name = str(patient.get("Name", "") or self._patient_id).strip()
        self._page_index = 0
        self._actions = TreatRecordActions(
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id,
            patient_name=self._patient_name,
            logger=self._logger,
        )
        self._update_title()
        self._load_records()

    def refresh(self) -> None:
        if self._patient_id:
            self._load_records()
        else:
            self.clear_records()

    def clear_records(self) -> None:
        self._all_records = []
        self._filtered_records = []
        self._page_index = 0
        self._update_title()
        self._apply_filter()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout_loaded_ui()
        old_page_size = self._page_size
        self._recalculate_page_size()
        if self._page_size != old_page_size:
            self._refresh_page()
        elif self._pagination_frame is not None:
            self._layout_pagination_position()

    def _setup_panel_background(self, container: Optional[QWidget]) -> None:
        self.setObjectName("embeddedTreatRecordPanel")
        self.setStyleSheet("QWidget#embeddedTreatRecordPanel { background-color: #FFFFFF; }")

        for widget in (container, self, self.ui):
            if widget is None:
                continue
            widget.setAttribute(Qt.WA_StyledBackground, True)
            widget.setAutoFillBackground(True)
            palette = widget.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
            widget.setPalette(palette)

        if container is not None:
            container.setStyleSheet(
                container.styleSheet()
                + "\nQWidget#widget_patient_treat_record { background-color: #FFFFFF; }"
            )

        self.ui.setStyleSheet(
            self.ui.styleSheet()
            + "\nQWidget#Form { background-color: #FFFFFF; border: none; border-radius: 0; }"
        )

    def _setup_connections(self) -> None:
        back_btn = get_ui_attr(self.ui, "pushButton")
        if back_btn is not None:
            back_btn.hide()

        export_btn = get_ui_attr(self.ui, "pushButton_2")
        if export_btn is not None:
            export_btn.setText("导出")
            export_btn.setStyleSheet(
                "QPushButton {"
                "background: transparent;"
                "border: 1px solid #4B86FC;"
                "border-radius: 10px;"
                "color: #4B86FC;"
                "padding: 6px 12px;"
                "}"
                "QPushButton:hover { background: rgba(75,134,252,0.08); }"
                "QPushButton:pressed { background: rgba(75,134,252,0.16); }"
            )
        safe_connect(self._logger, getattr(export_btn, "clicked", None), self._on_top_export_clicked)

        delete_btn = get_ui_attr(self.ui, "pushButton_3")
        if delete_btn is not None:
            delete_btn.setText("删除")
            delete_btn.setStyleSheet(
                "QPushButton {"
                "background: transparent;"
                "border: 1px solid #F04438;"
                "border-radius: 10px;"
                "color: #F04438;"
                "padding: 6px 12px;"
                "}"
                "QPushButton:hover { background: rgba(240,68,56,0.08); }"
                "QPushButton:pressed { background: rgba(240,68,56,0.16); }"
            )
        safe_connect(self._logger, getattr(delete_btn, "clicked", None), self._on_delete_clicked)

        self._table.bind_header_click()

    def _setup_record_table_background(self) -> None:
        table = get_ui_attr(self.ui, "tableWidget_treatrecord")
        if table is None:
            return

        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setAutoFillBackground(True)
        palette = table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F7F7F7"))
        table.setPalette(palette)
        table.setStyleSheet(
            table.styleSheet()
            + "\nQTableWidget#tableWidget_treatrecord {"
            + " background: #FFFFFF;"
            + " alternate-background-color: #F7F7F7;"
            + " }"
            + "\nQTableWidget#tableWidget_treatrecord::viewport { background: #FFFFFF; }"
        )

    def _build_header_controls(self) -> None:
        self._header_bg = QFrame(self.ui)
        self._header_bg.setStyleSheet("QFrame { background-color: #FFFFFF; border: none; }")
        self._header_bg.lower()

        self._header_title = QLabel("诊疗记录", self.ui)
        self._header_title.setStyleSheet("color: #1F1F1F; font-size: 18px; font-weight: 600;")

        self._search_wrap = QFrame(self.ui)
        self._search_wrap.setStyleSheet(
            "QFrame {"
            "background: #F7F8FC;"
            "border: 1px solid #E9EDF5;"
            "border-radius: 12px;"
            "}"
        )
        search_layout = QHBoxLayout(self._search_wrap)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.setSpacing(6)

        self._search_input = QLineEdit(self._search_wrap)
        self._search_input.setFrame(False)
        self._search_input.setPlaceholderText("请输入关键词")
        self._search_input.setStyleSheet(
            "QLineEdit {"
            "background: transparent;"
            "border: none;"
            "font-size: 13px;"
            "color: #1F1F1F;"
            "}"
        )
        safe_connect(self._logger, self._search_input.textChanged, self._on_search_text_changed)
        search_layout.addWidget(self._search_input, 1)

        search_icon = QLabel(self._search_wrap)
        search_icon.setFixedSize(16, 16)
        search_icon.setStyleSheet("border-image: url(:/treat/pic/treat_search.png);")
        search_layout.addWidget(search_icon)

        self._compare_btn = QPushButton("横向对比", self.ui)
        self._print_btn = QPushButton("打印", self.ui)
        for button in (self._compare_btn, self._print_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {"
                "background: #FFFFFF;"
                "border: 1px solid #7CA0FF;"
                "border-radius: 8px;"
                "color: #4B86FC;"
                "padding: 0 14px;"
                "}"
                "QPushButton:hover { background: #EEF4FF; }"
                "QPushButton:pressed { background: #DCE8FF; }"
            )
        safe_connect(self._logger, self._compare_btn.clicked, self._on_compare_clicked)
        safe_connect(self._logger, self._print_btn.clicked, self._on_top_print_clicked)
        self._build_pagination()

    def _build_pagination(self) -> None:
        if self._pagination_frame is not None:
            return

        self._footer_bg = QFrame(self.ui)
        self._footer_bg.setStyleSheet("QFrame { background-color: #FFFFFF; border: none; }")
        self._footer_bg.setAttribute(Qt.WA_StyledBackground, True)
        self._footer_bg.lower()

        pagination = QFrame(self.ui)
        pagination.setObjectName("treatRecordPagination")
        pagination.setMinimumHeight(self._PAGINATION_HEIGHT)
        pagination.setAttribute(Qt.WA_StyledBackground, True)
        pagination.setAutoFillBackground(False)
        pagination.setStyleSheet(
            "QFrame#treatRecordPagination { background-color: #FFFFFF; border: none; }"
            "QLabel { color: #98A2B3; font-size: 12px; padding: 2px 0; background: transparent; }"
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
        pagination.show()

    def _layout_pagination_position(self) -> None:
        if self._pagination_frame is None:
            return
        table = get_ui_attr(self.ui, "tableWidget_treatrecord")
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
        self._pagination_frame.raise_()

    def _recalculate_page_size(self) -> None:
        table = get_ui_attr(self.ui, "tableWidget_treatrecord")
        if table is None:
            return
        v_header = table.verticalHeader()
        row_height = v_header.defaultSectionSize() if v_header is not None else 46
        viewport_h = table.viewport().height()
        if viewport_h <= 0:
            return
        page_size = max(1, viewport_h // row_height)
        if page_size != self._page_size:
            self._page_size = page_size
            self._clamp_page_index()

    def _total_pages(self) -> int:
        if not self._filtered_records:
            return 0
        return int(ceil(len(self._filtered_records) / self._page_size))

    def _clamp_page_index(self) -> None:
        total_pages = self._total_pages()
        if total_pages <= 0:
            self._page_index = 0
            return
        self._page_index = min(max(self._page_index, 0), total_pages - 1)

    def _update_pagination(self) -> None:
        if self._pagination_frame is None:
            return
        total = len(self._filtered_records)
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
        self._recalculate_page_size()
        self._clamp_page_index()
        start = self._page_index * self._page_size
        end = start + self._page_size
        page_records = self._filtered_records[start:end]
        self._table.load_records(
            page_records,
            on_view_clicked=self._on_pdf_clicked,
            patient_name=self._patient_name,
        )
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

    def _relayout_loaded_ui(self) -> None:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        self.ui.resize(width, height)

        title_bg = get_ui_attr(self.ui, "label")
        if title_bg is not None:
            title_bg.setGeometry(0, 0, width, self._HEADER_HEIGHT)

        self._header_bg.setGeometry(0, 0, width, self._HEADER_HEIGHT)
        self._header_bg.lower()

        table = get_ui_attr(self.ui, "tableWidget_treatrecord")
        body_h = max(height - self._HEADER_HEIGHT - self._PAGINATION_HEIGHT, 0)
        if table is not None:
            table.setGeometry(0, self._HEADER_HEIGHT, width, body_h)

        footer_y = self._HEADER_HEIGHT + body_h
        footer_h = max(height - footer_y, 0)
        if hasattr(self, "_footer_bg"):
            self._footer_bg.setGeometry(0, footer_y, width, footer_h)
            self._footer_bg.lower()
        self._layout_pagination_position()

        title_tip = get_ui_attr(self.ui, "label_treatrecordtip")
        if title_tip is not None:
            title_tip.hide()

        export_btn = get_ui_attr(self.ui, "pushButton_2")
        delete_btn = get_ui_attr(self.ui, "pushButton_3")
        button_width = 82
        button_height = 34
        top_y = 18
        gap = 10
        right = width - 16

        if delete_btn is not None:
            delete_btn.setGeometry(right - button_width, top_y, button_width, button_height)
            right -= button_width + gap

        if export_btn is not None:
            export_btn.setGeometry(right - button_width, top_y, button_width, button_height)
            right -= button_width + gap

        self._print_btn.setGeometry(right - button_width, top_y, button_width, button_height)
        right -= button_width + gap

        self._compare_btn.setGeometry(right - 92, top_y, 92, button_height)
        right -= 92 + gap

        search_width = min(220, max(120, right - 170))
        self._search_wrap.setGeometry(max(right - search_width, 150), 14, search_width, 40)
        self._header_title.move(16, 22)

    def _load_records(self) -> None:
        if not self._session_app or not self._patient_id:
            self.clear_records()
            return
        try:
            records = self._session_app.get_patient_treat_sessions_by_patient(self._patient_id)
        except Exception:
            self._logger.exception("加载患者治疗记录失败")
            records = []
        self._all_records = list(records or [])
        self._apply_filter()

    def _update_title(self) -> None:
        self._header_title.setText("诊疗记录")

    def _apply_filter(self) -> None:
        keyword = self._search_input.text().strip().lower() if hasattr(self, "_search_input") else ""
        records = self._all_records
        if keyword:
            filtered_records: list[dict] = []
            for record in records:
                values = [
                    self._patient_name,
                    record.get("Paradigm", ""),
                    record.get("StimSchemeAB", ""),
                    record.get("StimPosition", ""),
                    record.get("StimFreqAB", ""),
                    record.get("TotalTrainDuration", ""),
                    record.get("UpdateTime", ""),
                ]
                haystack = " ".join(str(value or "").lower() for value in values)
                if keyword in haystack:
                    filtered_records.append(record)
            records = filtered_records
        self._filtered_records = list(records)
        self._refresh_page()

    def _on_search_text_changed(self, _text: str) -> None:
        self._page_index = 0
        self._apply_filter()

    def _on_top_export_clicked(self) -> None:
        if self._actions is None:
            TipsDialog.show_tips(self, "请先选择患者")
            return
        rows_to_export, _session_ids = self._table.get_selected_session_ids()
        if not rows_to_export:
            TipsDialog.show_tips(self, "请先勾选需要导出的治疗记录")
            return
        if len(rows_to_export) > 1:
            TipsDialog.show_tips(self, "暂仅支持单条导出，请只勾选一条记录")
            return
        self._actions.export_pdf_row(rows_to_export[0], self._table)

    def _on_delete_clicked(self) -> None:
        if self._actions is None:
            TipsDialog.show_tips(self, "请先选择患者")
            return
        self._actions.delete_selected(self._table)
        self._load_records()

    def _on_print_clicked(self, row: int) -> None:
        if self._actions is not None:
            self._actions.print_row(row)

    def _on_top_print_clicked(self) -> None:
        rows_to_print, _session_ids = self._table.get_selected_session_ids()
        if not rows_to_print:
            TipsDialog.show_tips(self, "请先勾选需要打印的治疗记录")
            return
        if len(rows_to_print) > 1:
            TipsDialog.show_tips(self, "暂仅支持单条打印，请只勾选一条记录")
            return
        self._on_print_clicked(rows_to_print[0])

    def _on_compare_clicked(self) -> None:
        if not self._patient_id:
            TipsDialog.show_tips(self, "请先选择患者")
            return
        _rows, session_ids = self._table.get_selected_session_ids()
        if len(session_ids) < 2:
            TipsDialog.show_tips(self, "请至少勾选两条治疗记录进行横向对比")
            return
        dialog = RecordCompareDialog(
            self,
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id,
            patient_name=self._patient_name,
            session_ids=session_ids,
        )
        dialog.exec()

    def _on_pdf_clicked(self, row: int) -> None:
        if self._actions is not None:
            self._actions.pdf_row(row, self._table)

    def _on_export_pdf_clicked(self, row: int) -> None:
        if self._actions is not None:
            self._actions.export_pdf_row(row, self._table)


class MainWindowReportPage:
    REPORT_TAB_INDEX = 4

    def __init__(self, host) -> None:
        self._host = host
        self.ui = host.ui
        self.logger = host.logger
        self._patients_panel: Optional[ReportPatientsPanel] = None
        self._treat_record_panel: Optional[EmbeddedTreatRecordPanel] = None
        self._current_patient_id: Optional[str] = None

    def init_ui(self) -> None:
        self._ensure_panels()
        self.refresh()

    def open_for_patient(self, patient: dict) -> None:
        """跳转到诊疗记录页并展示指定患者及其记录。"""
        patient_id = str(patient.get("PatientId") or "").strip()
        if not patient_id:
            TipsDialog.show_tips(self._host, "患者病历号为空")
            return

        self._current_patient_id = patient_id
        tab_widget = get_ui_attr(self.ui, "tabWidget")
        nav = getattr(self._host, "_nav", None)
        report_tab_index = self.REPORT_TAB_INDEX

        if tab_widget is not None and 0 <= report_tab_index < tab_widget.count():
            prev_index = getattr(self._host, "_current_tab_index", 0)
            if prev_index == 0:
                try:
                    self._host.treat_controller.on_exit_treat_page()
                except Exception:
                    self.logger.exception("离开治疗页时清理状态失败")
            self._host._report_selected = True
            tab_widget.setCurrentIndex(report_tab_index)
            self._host._current_tab_index = report_tab_index

        if nav is not None:
            nav.update_button_states()

        self._ensure_panels()
        selected: Optional[dict] = None
        if self._patients_panel is not None:
            selected = self._patients_panel.select_patient_by_id(patient_id, clear_search=True)
            if selected is not None:
                self._current_patient_id = self._patient_key(selected)
        if self._treat_record_panel is not None:
            self._treat_record_panel.set_patient(selected or patient)

    def refresh(self) -> None:
        self._ensure_panels()
        if self._patients_panel is None or self._treat_record_panel is None:
            return
        selected_patient = self._patients_panel.refresh(selected_patient_id=self._current_patient_id)
        if selected_patient:
            self._current_patient_id = self._patient_key(selected_patient)
        self._treat_record_panel.set_patient(selected_patient)

    def _ensure_panels(self) -> None:
        if self._patients_panel is None:
            container = get_ui_attr(self.ui, "widget_patients_record")
            if container is not None:
                layout = container.layout()
                if layout is None:
                    layout = QVBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(0)
                self._patients_panel = ReportPatientsPanel(self._host.patient_app, self.logger, container)
                layout.addWidget(self._patients_panel)
                safe_connect(self.logger, self._patients_panel.patient_selected, self.on_patient_selected)
                safe_connect(self.logger, self._patients_panel.export_clicked, self._on_export_patient_clicked)
                safe_connect(self.logger, self._patients_panel.delete_clicked, self._on_delete_patient_clicked)

        if self._treat_record_panel is None:
            container = get_ui_attr(self.ui, "widget_patient_treat_record")
            if container is not None:
                layout = container.layout()
                if layout is None:
                    layout = QVBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(0)
                self._treat_record_panel = EmbeddedTreatRecordPanel(
                    session_app=self._host.session_app,
                    report_app=self._host.report_app,
                    logger=self.logger,
                    parent=container,
                )
                layout.addWidget(self._treat_record_panel)

    def on_patient_selected(self, patient: dict) -> None:
        self._current_patient_id = self._patient_key(patient)
        if self._treat_record_panel is not None:
            self._treat_record_panel.set_patient(patient)

    def _on_export_patient_clicked(self) -> None:
        patient = self._get_current_patient()
        if not patient:
            TipsDialog.show_tips(self._host, "请先选择患者")
            return
        if not getattr(self._host, "session_app", None):
            TipsDialog.show_tips(self._host, "未找到治疗记录服务")
            return

        patient_id = str(patient.get("PatientId", "") or "").strip()
        patient_name = str(patient.get("Name", "") or patient_id).strip()
        try:
            records = self._host.session_app.get_patient_treat_sessions_by_patient(patient_id)
        except Exception:
            self.logger.exception("导出患者治疗记录失败")
            TipsDialog.show_tips(self._host, "加载治疗记录失败，无法导出")
            return

        if not records:
            TipsDialog.show_tips(self._host, "当前患者暂无治疗记录")
            return

        default_name = f"{patient_name or patient_id}_治疗记录.csv"
        path, _ = get_save_file_name(
            self._host,
            "导出患者治疗记录",
            default_name,
            "CSV 文件 (*.csv)",
        )
        if not path or not path.strip():
            return

        try:
            with open(path.strip(), "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["患者姓名", "病历号", "模式", "方案名称", "刺激部位", "刺激间隔(Hz)", "治疗时长", "治疗时间"])
                for record in records:
                    writer.writerow([
                        patient_name,
                        patient_id,
                        record.get("Paradigm", ""),
                        TreatRecordTable._map_scheme_name(record.get("StimSchemeAB", "")),
                        TreatRecordTable._map_stim_position(record.get("StimPosition", "")),
                        TreatRecordTable._map_stim_interval(record.get("StimFreqAB", "")),
                        record.get("TotalTrainDuration", ""),
                        record.get("UpdateTime", ""),
                    ])
        except Exception:
            self.logger.exception("写入患者治疗记录 CSV 失败")
            TipsDialog.show_tips(self._host, "导出失败，请检查保存路径")
            return

        TipsDialog.show_tips(self._host, "导出成功")

    def _on_delete_patient_clicked(self) -> None:
        patient = self._get_current_patient()
        if not patient:
            TipsDialog.show_tips(self._host, "请先选择患者")
            return

        patient_id = str(patient.get("PatientId", "") or "").strip()
        patient_name = str(patient.get("Name", "") or patient_id).strip()
        if not patient_id:
            TipsDialog.show_tips(self._host, "当前患者病历号为空，无法删除")
            return

        if not TipsDialog.show_confirm(self._host, f"确定删除患者「{patient_name or patient_id}」及其相关信息？"):
            return

        if getattr(self._host, "report_app", None):
            try:
                self._host.report_app.delete_reports_by_patient(patient_id)
            except Exception:
                self.logger.exception("删除患者关联报告失败")

        try:
            ok = self._host.patient_app.delete_patient(patient_id)
        except Exception:
            self.logger.exception("删除患者失败")
            TipsDialog.show_tips(self._host, "删除患者失败")
            return

        if not ok:
            TipsDialog.show_tips(self._host, "删除患者失败")
            return

        if hasattr(self._host, "clear_treat_context_if_patient_removed"):
            try:
                self._host.clear_treat_context_if_patient_removed(patient_id)
            except Exception:
                self.logger.exception("报表页删除患者后清理治疗上下文失败")

        self._current_patient_id = None
        self.refresh()
        TipsDialog.show_tips(self._host, "删除患者成功")

    def _get_current_patient(self) -> Optional[dict]:
        if self._patients_panel is None:
            return None
        patient = self._patients_panel.current_patient()
        if patient:
            self._current_patient_id = self._patient_key(patient)
        return patient

    @staticmethod
    def _patient_key(patient: Optional[dict]) -> Optional[str]:
        if not patient:
            return None
        text = str(patient.get("PatientId") or patient.get("Name") or "").strip()
        return text or None
