from __future__ import annotations

import logging
from math import ceil
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _PatientCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, patient: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._patient = patient
        self._selected = False
        self._build_ui()
        self._apply_style()

    def patient(self) -> Dict[str, Any]:
        return self._patient

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._patient)
        super().mousePressEvent(event)

    def _build_ui(self) -> None:
        self.setObjectName("patientCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(PatientSelectPanel.CARD_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        avatar = QLabel(self._get_avatar_text())
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            "background-color: #F2F4F7;"
            "border-radius: 8px;"
            "color: #8E8E93;"
            "font-size: 13px;"
            "font-weight: 600;"
        )
        avatar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(avatar, 0, Qt.AlignVCenter)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)

        name_label = QLabel(str(self._patient.get("Name", "") or "未命名"))
        name_label.setStyleSheet(
            "color: #1F1F1F; font-size: 14px; font-weight: 600; margin: 0; padding: 0;"
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        name_row.addWidget(name_label)

        meta_text = self._build_meta_text()
        if meta_text:
            meta_label = QLabel(meta_text)
            meta_label.setStyleSheet("color: #8E8E93; font-size: 11px;")
            meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            name_row.addWidget(meta_label)

        name_row.addStretch()
        info_layout.addLayout(name_row)

        visit_label = QLabel(f"入院时间：{self._format_visit_time()}")
        visit_label.setStyleSheet("color: #6B7280; font-size: 11px; margin: 0; padding: 0;")
        visit_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info_layout.addWidget(visit_label)

        layout.addLayout(info_layout, 1)

    def _get_avatar_text(self) -> str:
        name = str(self._patient.get("Name", "") or "").strip()
        return name[:1] or "?"

    def _build_meta_text(self) -> str:
        sex = str(self._patient.get("Sex", "") or "").strip()
        age = self._patient.get("Age")
        age_text = ""
        if age not in (None, ""):
            age_text = f"{age}岁"
        return " ".join(part for part in (sex, age_text) if part)

    def _format_visit_time(self) -> str:
        visit_time = str(self._patient.get("VisitTime", "") or "").strip()
        if not visit_time:
            return "--"
        return visit_time.replace("/", "-")

    def _apply_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                "QFrame#patientCard {"
                "background-color: #FFFFFF;"
                "border: 2px solid #4B86FC;"
                "border-radius: 8px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame#patientCard {"
                "background-color: #FFFFFF;"
                "border: 1px solid #E8ECF3;"
                "border-radius: 8px;"
                "}"
                "QFrame#patientCard:hover {"
                "border: 1px solid #C8D7FF;"
                "}"
            )


class PatientSelectPanel(QWidget):
    patient_selected = Signal(dict)
    patient_cleared = Signal()
    PAGE_SIZE = 10
    CARD_HEIGHT = 67
    CARD_SPACING = 8
    LIST_TOP_GAP = 20
    PAGINATION_TOP_GAP = 10

    def __init__(self, patient_app=None, parent: Optional[QWidget] = None, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(parent)
        self._logger = logger or logging.getLogger(__name__)
        self.patient_app = patient_app
        self._cards: List[_PatientCard] = []
        self._all_patients: List[Dict[str, Any]] = []
        self._selected_patient_id: Optional[str] = None
        self._page_index = 0
        self._page_size = self.PAGE_SIZE
        self._build_ui()
        self.refresh_patients()

    def focus_search(self) -> None:
        self._search_input.setFocus()
        self._search_input.selectAll()

    def refresh_patients(self, keyword: Optional[str] = None, selected_patient: Optional[Dict[str, Any]] = None) -> None:
        if selected_patient is not None:
            self._selected_patient_id = self._patient_key(selected_patient)

        text = self._search_input.text().strip()
        search_keyword = text if keyword is None else str(keyword).strip()

        patients: List[Dict[str, Any]] = []
        if self.patient_app:
            try:
                if search_keyword:
                    patients = self.patient_app.search_patients(search_keyword)
                else:
                    patients = self.patient_app.get_patients()
            except Exception:
                self._logger.exception("加载患者列表失败")
                patients = []

        self._all_patients = list(patients or [])
        if selected_patient is not None:
            self._sync_page_to_selected()
        else:
            self._clamp_page_index()
        self._render_cards()

    def set_selected_patient(self, patient: Optional[Dict[str, Any]]) -> None:
        self._selected_patient_id = self._patient_key(patient)
        self._update_card_selection()

    def _build_ui(self) -> None:
        self.setObjectName("patientSelectPanel")
        self.setStyleSheet(
            "QWidget#patientSelectPanel {"
            "background: #F7F8FC;"
            "border-radius: 8px;"
            "}"
        )

        root_layout = QVBoxLayout(self)
        # 给圆角容器预留内边距；底部略小，让分页器更贴近面板底边
        root_layout.setContentsMargins(6, 10, 6, 4)
        root_layout.setSpacing(6)

        search_wrap = QFrame()
        search_wrap.setObjectName("searchWrap")
        search_wrap.setStyleSheet(
            "QFrame#searchWrap {"
            "background: #F7F8FC;"
            "border: 1px solid #E9EDF5;"
            "border-radius: 12px;"
            "}"
        )
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(12, 8, 12, 8)
        search_layout.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索患者姓名")
        self._search_input.setFrame(False)
        self._search_input.setStyleSheet(
            "QLineEdit {"
            "background: transparent;"
            "border: none;"
            "font-size: 13px;"
            "color: #1F1F1F;"
            "}"
        )
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self._search_input, 1)

        search_icon = QLabel()
        search_icon.setFixedSize(16, 16)
        search_icon.setStyleSheet("border-image: url(:/treat/pic/treat_search.png);")
        search_layout.addWidget(search_icon, 0, Qt.AlignRight | Qt.AlignVCenter)

        root_layout.addWidget(search_wrap)

        self._list_widget = QWidget(self)
        self._list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)

        root_layout.addWidget(self._list_widget, 1)

        pagination = QFrame(self)
        pagination.setObjectName("patientPagination")
        pagination.setFixedHeight(30)
        pagination.setStyleSheet(
            "QFrame#patientPagination { background: transparent; }"
            "QLabel { color: #98A2B3; font-size: 12px; }"
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
            "border-radius: 8px;"
            "color: #8E8E93;"
            "font-size: 12px;"
            "padding: 1px 4px;"
            "}"
        )
        pagination_layout = QHBoxLayout(pagination)
        pagination_layout.setContentsMargins(0, 0, 0, 0)
        pagination_layout.setSpacing(6)
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
        pagination_layout.addStretch()
        root_layout.addSpacing(self.PAGINATION_TOP_GAP)
        root_layout.addWidget(pagination, 0)

    def _add_cards(self, cards: List[_PatientCard]) -> None:
        """卡片顶对齐，固定高度与间距。"""
        if not cards:
            return
        self._list_layout.setSpacing(self.CARD_SPACING)
        self._list_layout.addSpacing(self.LIST_TOP_GAP)
        for card in cards:
            self._list_layout.addWidget(card, 0)
        self._list_layout.addStretch(1)

    def _render_cards(self) -> None:
        self._clear_cards()
        self._cards = []
        self._page_size = self.PAGE_SIZE
        self._clamp_page_index()

        if not self._all_patients:
            self._list_layout.addStretch(1)
            empty = QLabel("暂无患者", self._list_widget)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #9AA2B1; font-size: 13px;")
            self._list_layout.addWidget(empty, 0, Qt.AlignCenter)
            self._list_layout.addStretch(1)
            self._update_pagination()
            return

        start = self._page_index * self._page_size
        end = start + self._page_size
        for patient in self._all_patients[start:end]:
            card = _PatientCard(patient, self._list_widget)
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)
        self._add_cards(self._cards)

        self._update_card_selection()
        self._update_pagination()

    def _clear_cards(self) -> None:
        while self._list_layout.count() > 0:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_card_selection(self) -> None:
        for card in self._cards:
            card.set_selected(self._patient_key(card.patient()) == self._selected_patient_id)

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

    def _on_prev_page(self) -> None:
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self._render_cards()

    def _on_next_page(self) -> None:
        total_pages = self._total_pages()
        if total_pages == 0 or self._page_index >= total_pages - 1:
            return
        self._page_index += 1
        self._render_cards()

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
        self._render_cards()

    def _on_search_text_changed(self, text: str) -> None:
        self.refresh_patients(keyword=text)

    def _on_card_clicked(self, patient: Dict[str, Any]) -> None:
        patient_key = self._patient_key(patient)
        if patient_key and patient_key == self._selected_patient_id:
            self._selected_patient_id = None
            self._update_card_selection()
            self.patient_cleared.emit()
            return
        self._selected_patient_id = patient_key
        self._update_card_selection()
        self.patient_selected.emit(patient)

    @staticmethod
    def _patient_key(patient: Optional[Dict[str, Any]]) -> Optional[str]:
        if not patient:
            return None
        row_id = patient.get("RowId")
        if row_id is not None and str(row_id).strip() != "":
            try:
                return f"row:{int(row_id)}"
            except (TypeError, ValueError):
                pass
        patient_id = str(patient.get("PatientId") or "").strip()
        name = str(patient.get("Name") or "").strip()
        visit_time = str(patient.get("VisitTime") or "").strip()
        composite = "|".join((patient_id, name, visit_time))
        return composite or None
