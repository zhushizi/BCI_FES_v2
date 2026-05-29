from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QTableWidgetItem

from ui.core.base_dialog import BaseUiDialog
from ui.core.dialog_overlay import exec_print_dialog, get_save_file_name
from ui.core.utils import get_ui_attr, safe_connect
from ui.dialogs.tips_dialog import TipsDialog
from ui.report import build_report_html, default_pdf_filename, generate_and_open_pdf

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = UI_ROOT / "record_compare.ui"


class RecordCompareDialog(BaseUiDialog):
    def __init__(
        self,
        parent=None,
        *,
        session_app=None,
        report_app=None,
        patient_id: str = "",
        patient_name: str = "",
        session_ids: list[int] | None = None,
    ) -> None:
        super().__init__(parent=parent, ui_path=UI_PATH, layout_spacing=0)
        self._logger = logging.getLogger(__name__)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.resize(1360, 920)

        self._session_app = session_app
        self._report_app = report_app
        self._patient_id = str(patient_id or "").strip()
        self._patient_name = str(patient_name or self._patient_id).strip()
        self._session_ids = [int(sid) for sid in (session_ids or []) if sid]
        self._records: list[dict] = []
        self._current_index = 0

        self._setup_table()
        self._setup_connections()
        self._load_records()

    def _setup_table(self) -> None:
        table = get_ui_attr(self.ui, "tableWidget_compare_records")
        if table is None:
            return
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().resizeSection(0, 44)
        table.horizontalHeader().resizeSection(1, 250)
        table.verticalHeader().setVisible(False)

    def _setup_connections(self) -> None:
        close_btn = get_ui_attr(self.ui, "pushButton_close")
        safe_connect(self._logger, getattr(close_btn, "clicked", None), self.accept)

        table = get_ui_attr(self.ui, "tableWidget_compare_records")
        safe_connect(self._logger, getattr(table, "cellClicked", None), self._on_row_clicked)

        prev_btn = get_ui_attr(self.ui, "pushButton_prev")
        next_btn = get_ui_attr(self.ui, "pushButton_next")
        print_btn = get_ui_attr(self.ui, "pushButton_print")
        export_btn = get_ui_attr(self.ui, "pushButton_export")
        safe_connect(self._logger, getattr(prev_btn, "clicked", None), self._on_prev_clicked)
        safe_connect(self._logger, getattr(next_btn, "clicked", None), self._on_next_clicked)
        safe_connect(self._logger, getattr(print_btn, "clicked", None), self._on_print_clicked)
        safe_connect(self._logger, getattr(export_btn, "clicked", None), self._on_export_clicked)

    def _load_records(self) -> None:
        self._records = []
        if not self._session_app:
            return

        for session_id in self._session_ids:
            try:
                detail = self._session_app.get_patient_treat_session_by_session_id(session_id)
            except Exception:
                self._logger.exception("加载横向对比记录失败: session_id=%s", session_id)
                detail = None
            if detail:
                self._records.append(detail)

        if not self._records:
            TipsDialog.show_tips(self, "未找到可对比的治疗记录")
            self.accept()
            return

        self._populate_table()
        self._set_current_index(0)

    def _populate_table(self) -> None:
        table = get_ui_attr(self.ui, "tableWidget_compare_records")
        if table is None:
            return

        table.blockSignals(True)
        table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            dot_item = QTableWidgetItem("●" if row == self._current_index else "○")
            dot_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, dot_item)

            time_item = QTableWidgetItem(str(record.get("UpdateTime", "") or ""))
            time_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, time_item)

            paradigm_item = QTableWidgetItem(str(record.get("Paradigm", "") or ""))
            paradigm_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, paradigm_item)

        table.selectRow(self._current_index)
        table.blockSignals(False)
        self._update_page_info()

    def _set_current_index(self, index: int) -> None:
        if not self._records:
            return
        self._current_index = max(0, min(index, len(self._records) - 1))
        self._populate_table()
        self._render_current_report()

    def _render_current_report(self) -> None:
        browser = get_ui_attr(self.ui, "textBrowser_report")
        if browser is None or not self._records:
            return
        record = self._records[self._current_index]
        session_id = record.get("SessionId")
        html_content = build_report_html(
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id,
            patient_name=self._patient_name,
            session_id=session_id,
            record_data=record,
            embed_images_for_web=True,
        )
        browser.setHtml(html_content or "<p>暂无报告内容</p>")

    def _update_page_info(self) -> None:
        label = get_ui_attr(self.ui, "label_page_info")
        if label is None:
            return
        total = len(self._records)
        current = self._current_index + 1 if total else 0
        label.setText(f"{current}/{total}")

    def _on_row_clicked(self, row: int, _column: int) -> None:
        self._set_current_index(row)

    def _on_prev_clicked(self) -> None:
        self._set_current_index(self._current_index - 1)

    def _on_next_clicked(self) -> None:
        self._set_current_index(self._current_index + 1)

    def _on_print_clicked(self) -> None:
        if not self._records:
            return
        browser = get_ui_attr(self.ui, "textBrowser_report")
        if browser is None:
            return
        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if exec_print_dialog(dialog) == 0:
            return
        doc = QTextDocument()
        doc.setHtml(browser.toHtml())
        doc.print_(printer)

    def _on_export_clicked(self) -> None:
        if not self._records:
            return
        record = self._records[self._current_index]
        session_id = record.get("SessionId")
        default_name = default_pdf_filename(self._patient_id or self._patient_name or "诊疗报告", "诊疗报告")
        path, _ = get_save_file_name(
            self,
            "导出 PDF",
            default_name,
            "PDF 文件 (*.pdf)",
        )
        if not path or not path.strip():
            return
        result = generate_and_open_pdf(
            session_app=self._session_app,
            report_app=self._report_app,
            patient_id=self._patient_id,
            patient_name=self._patient_name,
            session_id=session_id,
            record_data=record,
            save_path=path.strip(),
        )
        if result is None:
            TipsDialog.show_tips(self, "导出失败，请查看日志")
